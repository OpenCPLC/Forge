#-------------------------------------------------------------------------------------- Bootloader

# Bootloader of Core, `.boot/main.c`, compiled with `boot.h` of this project
# A build packs the one of `boot/`: under `key` the development key of this computer stands
# for every product key and the floors stay in the slot, so nothing on the board stays for good
# `dist` packs the one of `boot-dist/`: the product keys, floors in OTP
BOOT_kB := ${BOOT_kB}
# Development key of this computer, empty for a `plain` bootloader
BOOT_DEV_KEY := ${BOOT_DEV_KEY}
BOOT_DEV = $(if $(BOOT_DEV_KEY),-DBOOT_DEV_KEY=\"$(BOOT_DEV_KEY)\")

BOOT_C = ${BOOT_C}

BOOT_S = ${BOOT_S}

BOOT_INCLUDES = ${BOOT_INCLUDES}

BOOT_DEFS = ${BOOT_DEFS}
BOOT_CFLAGS = $(MCU) $(BOOT_DEFS) -Os -Wall -fdata-sections -ffunction-sections
BOOT_CFLAGS += -g -gdwarf-2 -MMD -MP -MF"$(@:%.o=%.d)"
BOOT_LDFLAGS = $(MCU) -specs=nano.specs -T$(BUILD)/boot.ld $(LIBS)
BOOT_LDFLAGS += -Wl,--no-warn-rwx-segment,-Map=$(@:.elf=.map),--cref -Wl,--gc-sections
BOOT_OBJECTS := $(BOOT_C:.c=.o) $(BOOT_S:.s=.o)

$(BUILD)/boot/%.o: $(OPENCPLC)/%.c $(CONFIG_DEPS)
	@$(call MKDIR,$(patsubst %/,%,$(dir $@)))
	$(CC) -c $(BOOT_CFLAGS) $(BOOT_DEV) $(BOOT_INCLUDES) $< -o $@

$(BUILD)/boot/%.o: $(OPENCPLC)/%.s $(CONFIG_DEPS)
	@$(call MKDIR,$(patsubst %/,%,$(dir $@)))
	$(AS) -c $(MCU) $(BOOT_DEFS) -Os $< -o $@

$(BUILD)/boot-dist/%.o: $(OPENCPLC)/%.c $(CONFIG_DEPS)
	@$(call MKDIR,$(patsubst %/,%,$(dir $@)))
	$(CC) -c $(BOOT_CFLAGS) $(BOOT_INCLUDES) $< -o $@

$(BUILD)/boot-dist/%.o: $(OPENCPLC)/%.s $(CONFIG_DEPS)
	@$(call MKDIR,$(patsubst %/,%,$(dir $@)))
	$(AS) -c $(MCU) $(BOOT_DEFS) -Os $< -o $@

$(BUILD)/boot/boot.elf: $(addprefix $(BUILD)/boot/,$(BOOT_OBJECTS)) $(BUILD)/boot.ld
	$(CC) $(filter %.o,$^) $(BOOT_LDFLAGS) -o $@
	@cd $(WORKSPACE) && $(FORGE) -z $@ $(BOOT_kB) $(RAM_kB)

$(BUILD)/boot-dist/boot.elf: $(addprefix $(BUILD)/boot-dist/,$(BOOT_OBJECTS)) $(BUILD)/boot.ld
	$(CC) $(filter %.o,$^) $(BOOT_LDFLAGS) -o $@
	@cd $(WORKSPACE) && $(FORGE) -z $@ $(BOOT_kB) $(RAM_kB)

# `make update` sends the update image of this build over the console, as a device takes one
# `FILE=` sends another image, `PORT=` names the console when the computer has several
update: build
	@cd $(WORKSPACE) && $(FORGE) --upload $(if $(FILE),$(FILE),$(BUILD)/$(TARGET)-dist.bin) $(PORT)

.PHONY: update

-include $(addprefix $(BUILD)/boot/,$(BOOT_OBJECTS:.o=.d))
-include $(addprefix $(BUILD)/boot-dist/,$(BOOT_OBJECTS:.o=.d))
