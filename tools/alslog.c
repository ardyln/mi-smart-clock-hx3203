// SPDX-License-Identifier: GPL-2.0-or-later
// Read-only HX3203 raw logger: alslog <seconds> <hz>
// Prints: epoch_ms ch0 ch1 off gain r0c  (via /dev/i2c-0, force, addr 0x44)
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <linux/i2c.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static int fd;

static int rd(unsigned char reg)
{
	unsigned char v;
	struct i2c_msg m[2] = {
		{ .addr = 0x44, .flags = 0, .len = 1, .buf = &reg },
		{ .addr = 0x44, .flags = I2C_M_RD, .len = 1, .buf = &v },
	};
	struct i2c_rdwr_ioctl_data d = { m, 2 };

	return ioctl(fd, I2C_RDWR, &d) == 2 ? v : -1;
}

int main(int argc, char **argv)
{
	int secs = argc > 1 ? atoi(argv[1]) : 60, hz = argc > 2 ? atoi(argv[2]) : 5;
	struct timespec t, s;
	long n = (long)secs * hz;

	fd = open("/dev/i2c-0", O_RDWR);
	if (fd < 0) { perror("i2c-0"); return 1; }
	setvbuf(stdout, NULL, _IOLBF, 0);
	clock_gettime(CLOCK_MONOTONIC, &s);
	for (long i = 0; i < n; i++) {
		int r08 = rd(0x08), r09 = rd(0x09), r0a = rd(0x0a), r0d = rd(0x0d),
		    r0e = rd(0x0e), r0f = rd(0x0f), r80 = rd(0x80), r81 = rd(0x81),
		    r0b = rd(0x0b), r0c = rd(0x0c);
		if ((r08 | r09 | r0a | r0d | r0e | r0f | r80 | r81) < 0) {
			puts("ERR");
		} else {
			long ch0 = (r09 << 8) | ((r0a & 15) << 4) | (r0f & 15) | ((long)(r0f & 0x30) << 12);
			long ch1 = (r08 << 3) | ((long)(r0d & 0x3f) << 11) | (r0e & 7);
			int off = ((r81 & 1) << 4) | (r80 >> 4);
			clock_gettime(CLOCK_REALTIME, &t);
			printf("%lld %ld %ld %d %d %d\n", t.tv_sec * 1000LL + t.tv_nsec / 1000000,
			       ch0, ch1, off, r0b, r0c);
		}
		s.tv_nsec += 1000000000L / hz;
		while (s.tv_nsec >= 1000000000L) { s.tv_nsec -= 1000000000L; s.tv_sec++; }
		clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &s, NULL);
	}
	return 0;
}
