# OmniScript: one binary, libc only.
VERSION := $(shell cat VERSION 2>/dev/null || echo 0.0.0)
CC ?= cc
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -DOMNI_VERSION=\"$(VERSION)\"
PREFIX ?= /usr/local

SRC := src/util.c src/lex.c src/parse.c src/eval.c src/draw.c src/sha256.c \
       src/update.c src/main.c

ifeq ($(OS),Windows_NT)
  EXE := .exe
  SRC += src/gui_win32.c
  LDLIBS += -lgdi32
else
  CFLAGS += -D_POSIX_C_SOURCE=200809L
  ifeq ($(NO_GUI),1)
    SRC += src/gui_stub.c
  else ifneq ($(wildcard /usr/include/X11/Xlib.h),)
    SRC += src/gui_x11.c
    CFLAGS += -DHAVE_X11
    LDLIBS += -lX11
  else
    SRC += src/gui_stub.c
    $(warning no X11 headers -- building without windows; drawings become files)
  endif
endif

OBJ := $(SRC:.c=.o)
BIN := omni$(EXE)

all: $(BIN)

$(BIN): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $(OBJ) $(LDFLAGS) $(LDLIBS)

%.o: %.c src/omni.h
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJ) $(BIN)

test: $(BIN)
	sh tests/run.sh ./$(BIN)

install: $(BIN)
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 755 $(BIN) $(DESTDIR)$(PREFIX)/bin/omni$(EXE)

.PHONY: all clean test install
