// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * One-shot, read-only check: does anything answer at the light/proximity
 * sensor addresses on I2C bus 0 (em3071x at 0x24, hx3203 at 0x44)?
 * Each address gets a single 1-byte read; nothing is written to any chip.
 * Init always fails, so the kernel unloads the module straight away.
 */
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/slab.h>

static const unsigned short addrs[] = { 0x24, 0x44 };

static int __init i2cprobe_init(void)
{
	struct i2c_adapter *adap;
	u8 *buf;
	int i;

	adap = i2c_get_adapter(0);
	if (!adap) {
		pr_info("i2cprobe: no adapter for bus 0\n");
		return -ENODEV;
	}
	buf = kzalloc(1, GFP_KERNEL);	/* heap buffer: the controller may DMA-map it */
	if (!buf) {
		i2c_put_adapter(adap);
		return -ENOMEM;
	}
	for (i = 0; i < ARRAY_SIZE(addrs); i++) {
		struct i2c_msg msg = {
			.addr = addrs[i], .flags = I2C_M_RD, .len = 1, .buf = buf,
		};
		int ret;

		*buf = 0;
		ret = i2c_transfer(adap, &msg, 1);
		pr_info("i2cprobe: bus 0 addr 0x%02x: %s (ret=%d byte=0x%02x)\n",
			addrs[i], ret == 1 ? "ANSWERED" : "no answer", ret, *buf);
	}
	kfree(buf);
	i2c_put_adapter(adap);
	return -EAGAIN;
}
module_init(i2cprobe_init);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("One-shot read-only I2C presence check for the ALS/PS addresses");
