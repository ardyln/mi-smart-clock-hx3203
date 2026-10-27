// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * HX3203 ambient light sensor for the Xiaomi Mi Smart Clock (X04G).
 *
 * Xiaomi's kernel only carries the EM3071X driver, so the MTK alsps
 * framework tears itself down at boot and the vendor sensor HAL never gets
 * /dev/m_als_misc. This module stands in for the light half of that
 * framework: it registers m_als_misc through the kernel's own sensor_attr
 * code (minor ID_LIGHT), exposes the alsactive/alsbatch/alsflush sysfs
 * protocol the HAL speaks, and polls the chip while the HAL has it enabled.
 *
 * Xiaomi's alsps_context pointer is NULL after boot and the code that
 * allocates it was freed with __init, so nothing of it is reused. The sensor_attr and
 * sensor_event helpers are not exported; they are looked up by name.
 *
 * Chip facts (measured on the panel, see ../../README.md): ID 0x21, gain
 * reg 0x0b = 4. ch0 is linear in light; calibrated against a phone placed
 * beside the panel (tradfri LED, 0-23 lx, residuals within 0.6 lx):
 * lux = 0.157 * (ch0 - 3.4). ch1 is left out: its dark level wanders by
 * ~10 counts with no change in light. No proximity part.
 */
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/kallsyms.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/poll.h>
#include <linux/regulator/consumer.h>
#include <linux/workqueue.h>

/* From MediaTek's sensors-1.0 headers (hwmsensor.h, sensor_attr.h, sensor_event.h) */
#define ID_LIGHT		4
#define ALS_MISC_DEV_NAME	"m_als_misc"

struct sensor_attr_t {
	unsigned char minor;
	const char *name;
	const struct file_operations *fops;
	struct list_head list;
	struct device *parent;
	struct device *this_device;
};

enum { DATA_ACTION, FLUSH_ACTION };

struct sensor_event {
	int64_t time_stamp;
	int8_t handle;
	int8_t flush_action;
	int8_t status;
	int8_t reserved;
	union {
		int32_t word[6];
		int8_t byte[0];
	};
} __packed;

struct sensorinfo_nonhub {
	char name[16];
};

static int (*p_sensor_attr_register)(struct sensor_attr_t *misc);
static int (*p_sensor_attr_deregister)(struct sensor_attr_t *misc);
static int (*p_sensor_input_event)(unsigned char handle,
				   const struct sensor_event *event);
static ssize_t (*p_sensor_event_read)(unsigned char handle, struct file *file,
				      char __user *buffer, size_t count,
				      loff_t *ppos);
static unsigned int (*p_sensor_event_poll)(unsigned char handle,
					   struct file *file, poll_table *wait);
static int (*p_sensorlist_register_deviceinfo)(int sensor,
					       struct sensorinfo_nonhub *devinfo);

static unsigned int lux_per_kcount = 157;
module_param(lux_per_kcount, uint, 0644);
MODULE_PARM_DESC(lux_per_kcount, "lux per 1000 ch0 counts (default 157)");

static unsigned int dark_x10 = 34;
module_param(dark_x10, uint, 0644);
MODULE_PARM_DESC(dark_x10, "ch0 dark level in tenths of a count (default 34)");

#define HX3203_ID		0x21
#define HX3203_REG_ID		0x00
#define HX3203_REG_ENABLE	0x01
#define HX3203_REG_GAIN		0x0b
#define HX3203_REG_CTRL		0x0c
#define HX3203_GAIN		0x04
#define HX3203_MIN_POLL_MS	100
#define HX3203_DEF_POLL_MS	200
#define HX3203_EMA_SHIFT	2	/* ~1 s smoothing at 200 ms polls */
#define HX3203_HYST_MLUX	750	/* the HAL only takes whole lux */

struct hx3203 {
	struct i2c_client *client;
	struct regulator *vdd;
	struct sensor_attr_t mdev;
	struct delayed_work poll;
	struct mutex lock;		/* enable state, chip power, poll period */
	unsigned int poll_ms;
	bool enabled;
	bool first_report;
	int avg16;			/* smoothed ch0, x16 */
	int last_lux;
};

static struct hx3203 *hx;

static int hx3203_write(struct hx3203 *chip, u8 reg, u8 val)
{
	return i2c_smbus_write_byte_data(chip->client, reg, val);
}

static int hx3203_power(struct hx3203 *chip, bool on)
{
	static const u8 seq[][2] = {
		{ 0x01, 0x70 }, { 0x02, 0x06 }, { 0x0c, 0x22 }, { 0x16, 0x36 },
		{ HX3203_REG_GAIN, HX3203_GAIN }, { 0x01, 0x74 }, { 0x0c, 0x22 },
	};
	int i, ret;

	if (!on)
		return hx3203_write(chip, HX3203_REG_CTRL, 0x02);

	for (i = 0; i < ARRAY_SIZE(seq); i++) {
		ret = hx3203_write(chip, seq[i][0], seq[i][1]);
		if (ret)
			return ret;
	}
	return 0;
}

static int hx3203_read_ch0(struct hx3203 *chip, int *ch0)
{
	static const u8 regs[] = { 0x09, 0x0a, 0x0f };
	u8 r[ARRAY_SIZE(regs)];
	int i, ret;

	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = i2c_smbus_read_byte_data(chip->client, regs[i]);
		if (ret < 0)
			return ret;
		r[i] = ret;
	}
	*ch0 = (r[0] << 8) | ((r[1] & 0x0f) << 4) | (r[2] & 0x0f) |
	       ((r[2] & 0x30) << 12);
	return 0;
}

static void hx3203_report(int value)
{
	struct sensor_event event = {
		.handle = ID_LIGHT,
		.flush_action = DATA_ACTION,
		.word[0] = value,
	};

	p_sensor_input_event(ID_LIGHT, &event);
}

static void hx3203_poll_work(struct work_struct *work)
{
	struct hx3203 *chip = container_of(work, struct hx3203, poll.work);
	int ch0, mlux;

	mutex_lock(&chip->lock);
	if (!chip->enabled)
		goto out;

	if (hx3203_read_ch0(chip, &ch0)) {
		dev_err_ratelimited(&chip->client->dev, "read failed\n");
	} else {
		if (chip->first_report)
			chip->avg16 = ch0 << 4;
		else
			chip->avg16 += ((ch0 << 4) - chip->avg16) >> HX3203_EMA_SHIFT;
		mlux = (chip->avg16 * 10 / 16 - (int)dark_x10) *
		       (int)lux_per_kcount / 10;
		if (mlux < 0)
			mlux = 0;

		/* Like the stock framework: nudge on-change listeners after enable. */
		if (chip->first_report) {
			chip->last_lux = (mlux + 500) / 1000;
			hx3203_report(chip->last_lux + 1);
			hx3203_report(chip->last_lux);
			chip->first_report = false;
		} else if (abs(mlux - chip->last_lux * 1000) >= HX3203_HYST_MLUX) {
			chip->last_lux = (mlux + 500) / 1000;
			hx3203_report(chip->last_lux);
		}
	}
	queue_delayed_work(system_power_efficient_wq, &chip->poll,
			   msecs_to_jiffies(chip->poll_ms));
out:
	mutex_unlock(&chip->lock);
}

static int hx3203_set_enable(struct hx3203 *chip, bool en)
{
	int ret = 0;

	mutex_lock(&chip->lock);
	if (en == chip->enabled)
		goto out;

	ret = hx3203_power(chip, en);
	if (ret) {
		dev_err(&chip->client->dev, "power %s failed: %d\n",
			en ? "on" : "off", ret);
		goto out;
	}
	chip->enabled = en;
	if (en) {
		chip->first_report = true;
		/* first conversion needs a moment after power-up */
		queue_delayed_work(system_power_efficient_wq, &chip->poll,
				   msecs_to_jiffies(chip->poll_ms));
	}
out:
	mutex_unlock(&chip->lock);
	if (!en)
		cancel_delayed_work_sync(&chip->poll);
	return ret;
}

/* sysfs protocol of the MTK alsps framework (/sys/class/sensor/m_als_misc) */
static ssize_t alsactive_store(struct device *dev, struct device_attribute *attr,
			       const char *buf, size_t count)
{
	int handle, en, ret;

	if (sscanf(buf, "%d,%d", &handle, &en) != 2)
		return -EINVAL;
	if (handle != ID_LIGHT)
		return count;	/* RGBW: not on this chip */
	ret = hx3203_set_enable(hx, en);
	return ret ? ret : count;
}

static ssize_t alsactive_show(struct device *dev, struct device_attribute *attr,
			      char *buf)
{
	return snprintf(buf, PAGE_SIZE, "%d\n", 1);	/* vender_div */
}

static ssize_t alsbatch_store(struct device *dev, struct device_attribute *attr,
			      const char *buf, size_t count)
{
	int handle, flag;
	long long delay_ns, latency_ns;

	if (sscanf(buf, "%d,%d,%lld,%lld", &handle, &flag, &delay_ns,
		   &latency_ns) != 4)
		return -EINVAL;
	if (handle != ID_LIGHT || delay_ns < 0)
		return count;

	mutex_lock(&hx->lock);
	hx->poll_ms = max_t(unsigned int, div_u64(delay_ns, NSEC_PER_MSEC),
			    HX3203_MIN_POLL_MS);
	if (hx->enabled)
		mod_delayed_work(system_power_efficient_wq, &hx->poll,
				 msecs_to_jiffies(hx->poll_ms));
	mutex_unlock(&hx->lock);
	return count;
}

static ssize_t alsflush_store(struct device *dev, struct device_attribute *attr,
			      const char *buf, size_t count)
{
	struct sensor_event event = {
		.handle = ID_LIGHT,
		.flush_action = FLUSH_ACTION,
	};
	int handle, ret;

	ret = kstrtoint(buf, 10, &handle);
	if (ret)
		return ret;
	if (handle == ID_LIGHT)
		p_sensor_input_event(ID_LIGHT, &event);
	return count;
}

static ssize_t zero_show(struct device *dev, struct device_attribute *attr,
			 char *buf)
{
	return snprintf(buf, PAGE_SIZE, "%d\n", 0);
}

static ssize_t alscali_store(struct device *dev, struct device_attribute *attr,
			     const char *buf, size_t count)
{
	return count;	/* the HAL may push NVRAM calibration; not used */
}

static DEVICE_ATTR(alsactive, 0644, alsactive_show, alsactive_store);
static DEVICE_ATTR(alsbatch, 0644, zero_show, alsbatch_store);
static DEVICE_ATTR(alsflush, 0644, zero_show, alsflush_store);
static DEVICE_ATTR(alsdevnum, 0644, zero_show, NULL);
static DEVICE_ATTR(alscali, 0644, NULL, alscali_store);

static struct attribute *als_attrs[] = {
	&dev_attr_alsactive.attr,
	&dev_attr_alsbatch.attr,
	&dev_attr_alsflush.attr,
	&dev_attr_alsdevnum.attr,
	&dev_attr_alscali.attr,
	NULL
};

static const struct attribute_group als_group = {
	.attrs = als_attrs,
};

static int light_open(struct inode *inode, struct file *file)
{
	return nonseekable_open(inode, file);
}

static ssize_t light_read(struct file *file, char __user *buffer, size_t count,
			  loff_t *ppos)
{
	return p_sensor_event_read(ID_LIGHT, file, buffer, count, ppos);
}

static unsigned int light_poll(struct file *file, poll_table *wait)
{
	return p_sensor_event_poll(ID_LIGHT, file, wait);
}

static const struct file_operations light_fops = {
	.owner = THIS_MODULE,
	.open = light_open,
	.read = light_read,
	.poll = light_poll,
};

static int hx3203_probe(struct i2c_client *client,
			const struct i2c_device_id *id)
{
	struct sensorinfo_nonhub info = { .name = "hx3203" };
	struct hx3203 *chip;
	int ret;

	if (hx)
		return -EBUSY;

	chip = devm_kzalloc(&client->dev, sizeof(*chip), GFP_KERNEL);
	if (!chip)
		return -ENOMEM;
	chip->client = client;
	chip->poll_ms = HX3203_DEF_POLL_MS;
	chip->last_lux = -1;
	mutex_init(&chip->lock);
	INIT_DELAYED_WORK(&chip->poll, hx3203_poll_work);

	/* DT: alsps-supply = vgp2 */
	chip->vdd = devm_regulator_get_optional(&client->dev, "alsps");
	if (IS_ERR(chip->vdd)) {
		if (PTR_ERR(chip->vdd) == -EPROBE_DEFER)
			return -EPROBE_DEFER;
		chip->vdd = NULL;
	} else {
		ret = regulator_enable(chip->vdd);
		if (ret)
			return ret;
		msleep(20);
	}

	ret = i2c_smbus_read_byte_data(client, HX3203_REG_ID);
	if (ret != HX3203_ID) {
		dev_err(&client->dev, "unexpected ID %d\n", ret);
		ret = ret < 0 ? ret : -ENODEV;
		goto err_power;
	}
	hx3203_write(chip, HX3203_REG_CTRL, 0x02);	/* idle until enabled */

	chip->mdev.minor = ID_LIGHT;
	chip->mdev.name = ALS_MISC_DEV_NAME;
	chip->mdev.fops = &light_fops;
	ret = p_sensor_attr_register(&chip->mdev);
	if (ret) {
		dev_err(&client->dev, "m_als_misc register failed: %d\n", ret);
		goto err_power;
	}
	ret = sysfs_create_group(&chip->mdev.this_device->kobj, &als_group);
	if (ret)
		goto err_attr;
	kobject_uevent(&chip->mdev.this_device->kobj, KOBJ_ADD);
	p_sensorlist_register_deviceinfo(ID_LIGHT, &info);

	i2c_set_clientdata(client, chip);
	hx = chip;
	dev_info(&client->dev, "HX3203 ready as %s\n", ALS_MISC_DEV_NAME);
	return 0;

err_attr:
	p_sensor_attr_deregister(&chip->mdev);
err_power:
	if (chip->vdd)
		regulator_disable(chip->vdd);
	return ret;
}

static int hx3203_remove(struct i2c_client *client)
{
	struct hx3203 *chip = i2c_get_clientdata(client);

	hx3203_set_enable(chip, false);
	sysfs_remove_group(&chip->mdev.this_device->kobj, &als_group);
	p_sensor_attr_deregister(&chip->mdev);
	if (chip->vdd)
		regulator_disable(chip->vdd);
	hx = NULL;
	return 0;
}

static const struct of_device_id hx3203_of_match[] = {
	{ .compatible = "mediatek,alsps-hx3203" },
	{ }
};
MODULE_DEVICE_TABLE(of, hx3203_of_match);

static const struct i2c_device_id hx3203_id[] = {
	{ "alsps-hx3203", 0 },
	{ }
};
MODULE_DEVICE_TABLE(i2c, hx3203_id);

static struct i2c_driver hx3203_driver = {
	.driver = {
		.name = "hx3203",
		.of_match_table = hx3203_of_match,
	},
	.probe = hx3203_probe,
	.remove = hx3203_remove,
	.id_table = hx3203_id,
};

/*
 * kallsyms hands back Thumb-2 function addresses with bit 0 clear; calling
 * through such a pointer would switch the CPU to ARM state. Set it again.
 */
#define LOOKUP(sym) do {						\
	unsigned long addr = kallsyms_lookup_name(#sym);		\
	if (!addr) {							\
		pr_err("hx3203: %s not found\n", #sym);			\
		return -ENOENT;						\
	}								\
	if (IS_ENABLED(CONFIG_THUMB2_KERNEL))				\
		addr |= 1;						\
	p_##sym = (void *)addr;						\
} while (0)

static int __init hx3203_init(void)
{
	LOOKUP(sensor_attr_register);
	LOOKUP(sensor_attr_deregister);
	LOOKUP(sensor_input_event);
	LOOKUP(sensor_event_read);
	LOOKUP(sensor_event_poll);
	LOOKUP(sensorlist_register_deviceinfo);
	return i2c_add_driver(&hx3203_driver);
}
module_init(hx3203_init);

static void __exit hx3203_exit(void)
{
	i2c_del_driver(&hx3203_driver);
}
module_exit(hx3203_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("HX3203 ambient light sensor as MTK m_als_misc (Xiaomi X04G)");
