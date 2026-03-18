NAME = ${NAME}
TARGET = ${PREFIX}$(subst /,-,$(NAME))
LIB = ${LIB_PATH}
PRO = ${PRO_PATH}
BUILD = ${BUILD_PATH}

C_SOURCES = \
${C_SOURCES}

ASM_SOURCES = \
${ASM_SOURCES}

PREFIX = arm-none-eabi-

ifdef GCC_PATH
CC = $(GCC_PATH)/$(PREFIX)gcc
AS = $(GCC_PATH)/$(PREFIX)gcc -x assembler-with-cpp
CP = $(GCC_PATH)/$(PREFIX)objcopy
SZ = $(GCC_PATH)/$(PREFIX)size
else
CC = $(PREFIX)gcc
AS = $(PREFIX)gcc -x assembler-with-cpp
CP = $(PREFIX)objcopy
SZ = $(PREFIX)size
endif
HEX = $(CP) -O ihex
BIN = $(CP) -O binary -S

CPU = ${CPU_FLAGS}
MCU = ${MCU_FLAGS}

AS_DEFS = ${C_DEFS}
C_DEFS = ${C_DEFS}

ASM_INCLUDES =

C_INCLUDES = \
${C_INCLUDES}

ASFLAGS = $(MCU) $(AS_DEFS) $(ASM_INCLUDES) -${OPT_LEVEL} -Wall -fdata-sections -ffunction-sections
CFLAGS = $(MCU) $(C_DEFS) $(C_INCLUDES) -${OPT_LEVEL} -Wall -fdata-sections -ffunction-sections
CFLAGS += -g -gdwarf-2
CFLAGS += -MMD -MP -MF"$(@:%.o=%.d)"

LD_SCRIPT = ${LD_FILE}

LIBS = -lc -lm -lnosys
LIBDIR =
LDFLAGS = $(MCU) -specs=nano.specs -T$(LD_SCRIPT) $(LIBDIR) $(LIBS)
LDFLAGS += -Wl,--no-warn-rwx-segment,-Map=$(BUILD)/$(TARGET).map,--cref -Wl,--gc-sections

all: $(BUILD)/$(TARGET).elf $(BUILD)/$(TARGET).hex $(BUILD)/$(TARGET).bin

OBJECTS = $(patsubst %.c,$(BUILD)/%.o,$(C_SOURCES))
C_DIRS := $(sort $(dir $(shell find . -name "*.c")))
# C_DIRS := $(sort $(shell powershell -Command "Get-ChildItem -Recurse -Filter *.c | Select-Object -ExpandProperty DirectoryName"))
vpath %.c $(C_DIRS)
OBJECTS += $(patsubst %.s,$(BUILD)/%.o,$(ASM_SOURCES))
ASM_DIRS := $(sort $(dir $(shell find . -name "*.s")))
# ASM_DIRS := $(sort $(shell powershell -Command "Get-ChildItem -Recurse -Filter *.s | Select-Object -ExpandProperty DirectoryName"))
vpath %.s $(ASM_DIRS)

$(OBJECTS): $(PRO)/main.h

$(BUILD)/%.o: %.c Makefile | $(dir $(BUILD)/%)
	@mkdir -p $(dir $@)
#	@cmd /c if not exist "$(subst /,\,$(dir $@))" mkdir "$(subst /,\,$(dir $@))"
	$(CC) -c $(CFLAGS) -Wa,-a,-ad,-alms=$(BUILD)/$(<:%.c=%.lst) $< -o $@

$(BUILD)/%.o: %.s Makefile | $(dir $(BUILD)/%)
	$(AS) -c $(CFLAGS) $< -o $@

$(BUILD)/$(TARGET).elf: $(OBJECTS) Makefile
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@
	$(SZ) $@

$(BUILD)/%.hex: $(BUILD)/%.elf | $(dir $(BUILD)/%)
	$(HEX) $< $@

$(BUILD)/%.bin: $(BUILD)/%.elf | $(dir $(BUILD)/%)
	$(BIN) $< $@

$(dir $(BUILD)/%):
	@mkdir -p $@
#	@if not exist "$(subst /,\,$@)" (mkdir "$(subst /,\,$@)")

OPENOCD = ${OPENOCD_PATH}openocd -f interface/stlink.cfg -f target/${OPENOCD_TARGET}.cfg -c

build: all

flash:
	$(OPENOCD) "program $(BUILD)/$(TARGET).elf verify reset exit"

run: all flash

clean:
	@if [ -d "$(BUILD)/$(LIB)" ]; then rm -rf "$(BUILD)/$(LIB)"; fi
#	@if exist "$(BUILD)\$(LIB)" (cmd /c "rmdir /s /q $(BUILD)\$(LIB)")
	@if [ -d "$(BUILD)/$(PRO)" ]; then rm -rf "$(BUILD)/$(PRO)"; fi
#	@if exist "$(BUILD)\$(PRO)" (cmd /c "rmdir /s /q $(BUILD)\$(PRO)")
	@find $(BUILD) -type f -name '$(TARGET).*' -exec rm -f {} +
#	@cmd /c "del /q $(BUILD)\$(TARGET).*"

clean_all:
	@if [ -d "$(BUILD)" ]; then rm -rf "$(BUILD)"; fi
#	@if exist "$(BUILD)" (cmd /c "rmdir /s /q $(BUILD)")

clr: clean
clr_all: clean_all

erase:
	$(OPENOCD) "init; halt; stm32g0x mass_erase 0; reset halt; exit"

.PHONY: all build flash run clean clean_all clr clr_all erase

-include $(shell find $(BUILD) -name "*.d" 2>/dev/null)