VERSION := $(shell cat VERSION 2>/dev/null || echo 1.0.2)
CC ?= $(shell command -v cc 2>/dev/null || command -v gcc 2>/dev/null || command -v clang 2>/dev/null || echo cc)
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -DOMNI_VERSION=\"$(VERSION)\"
PREFIX ?= /usr/local

SRC := src/util.c src/lex.c src/parse.c src/eval.c src/draw.c src/main.c

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
	rm -rf dist

test: $(BIN)
	@echo "no old tests, running simple smoke"
	./$(BIN) -e 'import draw; draw.window(100,100); draw.rect(0,0,50,50,"red"); draw.save("test.bmp")'
	./$(BIN) -e 'import pathlib; pathlib.write("test.txt","hi"); print(pathlib.read("test.txt"))'
	./$(BIN) -e 'import cmd; cmd.run("echo hello")'
	@echo "smoke ok"

install: $(BIN)
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 755 $(BIN) $(DESTDIR)$(PREFIX)/bin/omni$(EXE)

# Installers
dmg: $(BIN)
	./installer/macos/build-dmg.sh

deb: $(BIN)
	./installer/linux/build-deb.sh

rpm: $(BIN)
	./installer/linux/build-rpm.sh

exe:
	@echo "To build Windows EXE installer, on Windows run:"
	@echo "  installer\\windows\\build.bat"
	@echo "Or: powershell -ExecutionPolicy Bypass -File installer\\windows\\build.ps1"
	@echo "Requires Inno Setup 6: https://jrsoftware.org/isinfo.php"

dist: $(BIN)
	./installer/build-all.sh

.PHONY: all clean test install dmg deb rpm exe dist
