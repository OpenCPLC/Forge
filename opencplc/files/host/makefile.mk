NAME = ${NAME}
TARGET = ${PREFIX}$(subst /,-,$(NAME))
LIB = ${LIB_PATH}
PRO = ${PRO_PATH}
BUILD = ${BUILD_PATH}

C_SOURCES = \
${C_SOURCES}

CC = gcc

C_DEFS = ${C_DEFS}

C_INCLUDES = \
${C_INCLUDES}

CFLAGS = -std=c11 -${OPT_LEVEL} -Wall -Wextra $(C_DEFS) $(C_INCLUDES)
CFLAGS += -g -MMD -MP -MF"$(@:%.o=%.d)"

ifeq ($(OS),Windows_NT)
  LIBS = -lm -lbcrypt
  EXE = $(BUILD)/$(TARGET).exe
else
  LIBS = -lm -lpthread
  EXE = $(BUILD)/$(TARGET)
endif

all: $(EXE)

OBJECTS = $(patsubst %.c,$(BUILD)/%.o,$(C_SOURCES))
C_DIRS := $(sort $(dir $(shell find . -name "*.c")))
# C_DIRS := $(sort $(shell powershell -Command "Get-ChildItem -Recurse -Filter *.c | Select-Object -ExpandProperty DirectoryName"))
vpath %.c $(C_DIRS)

$(BUILD)/%.o: %.c Makefile
	@mkdir -p $(dir $@)
#	@cmd /c if not exist "$(subst /,\,$(dir $@))" mkdir "$(subst /,\,$(dir $@))"
	$(CC) -c $(CFLAGS) $< -o $@

$(EXE): $(OBJECTS) Makefile
	@mkdir -p $(dir $@)
#	@cmd /c if not exist "$(subst /,\,$(dir $@))" mkdir "$(subst /,\,$(dir $@))"
	$(CC) $(OBJECTS) $(LIBS) -o $@

build: all

run: all
	$(EXE)

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

dist: all
	cp $(EXE) $(PRO)/$(notdir $(EXE))
#	copy "$(subst /,\,$(EXE))" "$(subst /,\,$(PRO)\$(notdir $(EXE)))"

.PHONY: all build run clean clean_all clr clr_all dist

-include $(shell find $(BUILD) -name "*.d" 2>/dev/null)