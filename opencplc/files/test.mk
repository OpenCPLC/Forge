#------------------------------------------------------------------------------------------- Tests
# `make test` builds every `.tests/*.c` into a program for this computer,
# against Core compiled in test mode, and Forge runs them; `make test T=name` runs one
# Programs come from `$(wildcard)`, so a new test needs no reload

TEST_DIR := ${TEST_DIR}
TEST_BUILD := $(BUILD)/test

# Core of a test: `hal/host`, `lib` and `tst`, relative to `$(OPENCPLC)`
TEST_CORE_C = ${TEST_CORE_C}

TEST_INCLUDES = ${TEST_INCLUDES}

ifeq ($(OS),Windows_NT)
TEST_DEFS = -D_WIN64 ${TEST_DEFS}
TEST_LIBS = -lm -lbcrypt
TEST_EXT = .exe
else
TEST_DEFS = -D_GNU_SOURCE ${TEST_DEFS}
TEST_LIBS = -lm -lpthread
TEST_EXT =
endif

# A miss names its file from the workspace, as the console opens it
TEST_CFLAGS = -std=c11 $(OPT) -g -Wall -Wextra $(TEST_DEFS) $(TEST_INCLUDES)
TEST_CFLAGS += -fmacro-prefix-map=$(WORKSPACE)/=

TEST_OBJECTS := $(patsubst %.c,$(TEST_BUILD)/opencplc/%.o,$(TEST_CORE_C))
TEST_NAMES := $(basename $(notdir $(wildcard $(TEST_DIR)/*.c)))
TEST_PICK := $(or $(T),$(TEST_NAMES))
TEST_PROGRAMS := $(TEST_PICK:%=$(TEST_BUILD)/%$(TEST_EXT))

$(TEST_BUILD)/opencplc/%.o: $(OPENCPLC)/%.c $(CONFIG_DEPS)
	@$(call MKDIR,$(patsubst %/,%,$(dir $@)))
	gcc -c $(TEST_CFLAGS) -MMD -MP -MF"$(@:%.o=%.d)" $< -o $@

$(TEST_BUILD)/core.a: $(TEST_OBJECTS)
	ar rcs $@ $^

$(TEST_BUILD)/%$(TEST_EXT): $(TEST_DIR)/%.c $(TEST_BUILD)/core.a $(CONFIG_DEPS)
	gcc $(TEST_CFLAGS) -MMD -MP -MF"$(TEST_BUILD)/$*.d" $< $(TEST_BUILD)/core.a $(TEST_LIBS) -o $@

test: $(TEST_PROGRAMS)
	@$(if $(TEST_PICK),cd $(WORKSPACE) && $(FORGE) --test $(TEST_BUILD) $(TEST_PICK),echo No test programs in ${TEST_COLORED})

.PHONY: test

-include $(TEST_OBJECTS:.o=.d) $(TEST_PICK:%=$(TEST_BUILD)/%.d)
