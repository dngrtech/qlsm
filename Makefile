CC ?= gcc
FORCE_RATE_SRC := ql-assets/data/system-hooks/force_rate.c
FORCE_RATE_SO := ql-assets/data/system-hooks/force_rate.so
FORCE_RATE_BUILD := /tmp/qlsm-force_rate.verify.so

.PHONY: force-rate.so verify-system-hooks

force-rate.so:
	$(CC) -shared -fPIC -Wall -Wextra -Werror -Wl,--build-id=none -o $(FORCE_RATE_SO) $(FORCE_RATE_SRC)

verify-system-hooks:
	$(CC) -shared -fPIC -Wall -Wextra -Werror -Wl,--build-id=none -o $(FORCE_RATE_BUILD) $(FORCE_RATE_SRC)
	cmp $(FORCE_RATE_BUILD) $(FORCE_RATE_SO)
