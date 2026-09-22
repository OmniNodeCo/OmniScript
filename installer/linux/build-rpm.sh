#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 1.0.0)"
ARCH="$(uname -m)"
RPMARCH="x86_64"
if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then RPMARCH="aarch64"; fi

echo "==> OmniScript $VERSION Linux RPM ($RPMARCH) — OS integrated"

# Build omni if needed
if [ ! -f "$ROOT/omni" ]; then
  echo "    Building omni"
  make -C "$ROOT"
fi

DIST_DIR="$ROOT/dist"
mkdir -p "$DIST_DIR"

RPM_FILE="$DIST_DIR/omniscript-${VERSION}-1.${RPMARCH}.rpm"

# Try rpmbuild if available
if command -v rpmbuild >/dev/null 2>&1; then
  RPMBUILD_ROOT="$DIST_DIR/rpmbuild"
  rm -rf "$RPMBUILD_ROOT"
  mkdir -p "$RPMBUILD_ROOT"/{BUILD,RPMS,SOURCES,SPECS,BUILDROOT}

  # Prepare sources
  SOURCEDIR="$RPMBUILD_ROOT/SOURCES/omniscript-${VERSION}"
  mkdir -p "$SOURCEDIR"
  cp "$ROOT/omni" "$SOURCEDIR/" 2>/dev/null || true
  cp "$ROOT/README.md" "$SOURCEDIR/" 2>/dev/null || true
  cp "$ROOT/LICENSE" "$SOURCEDIR/" 2>/dev/null || true
  cp -r "$ROOT/examples" "$SOURCEDIR/" 2>/dev/null || true

  tar -czf "$RPMBUILD_ROOT/SOURCES/omniscript-${VERSION}.tar.gz" -C "$RPMBUILD_ROOT/SOURCES" "omniscript-${VERSION}"

  cat > "$RPMBUILD_ROOT/SPECS/omniscript.spec" <<SPEC
Name:           omniscript
Version:        $VERSION
Release:        1%{?dist}
Summary:        OmniScript — very very very simple language — type 'omni' and it reacts
License:        MIT
URL:            https://github.com/OmniNodeCo/OmniScript
Source0:        omniscript-%{version}.tar.gz
BuildArch:      $RPMARCH

%description
Tiny language with draw, cmd, pathlib modules.
Imports like Python: import draw, cmd, pathlib.
One binary, libc only.
After install, type 'omni' in terminal and it reacts.

%prep
%setup -q -n omniscript-%{version}

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/doc/omniscript
mkdir -p %{buildroot}/usr/share/omniscript/examples
mkdir -p %{buildroot}/usr/share/applications
install -m 755 omni %{buildroot}/usr/bin/omni
install -m 644 README.md %{buildroot}/usr/share/doc/omniscript/ 2>/dev/null || true
install -m 644 LICENSE %{buildroot}/usr/share/doc/omniscript/ 2>/dev/null || true
cp -r examples/* %{buildroot}/usr/share/omniscript/examples/ 2>/dev/null || true

cat > %{buildroot}/usr/share/applications/omniscript.desktop <<DESKTOP
[Desktop Entry]
Name=OmniScript
GenericName=OmniScript Language
Comment=Tiny language — draw, cmd, pathlib — type 'omni' in terminal
Exec=omni
Terminal=true
Type=Application
Categories=Development;
Keywords=omni;script;
DESKTOP

%post
echo "==> OmniScript $VERSION installed into OS"
echo "    Binary: /usr/bin/omni"
echo "    Now type in terminal and it reacts:"
echo "      omni --version"
echo "      omni"
echo "      omni /usr/share/omniscript/examples/01_hello.omni"
if [ -x /usr/bin/omni ]; then
  /usr/bin/omni --version 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications 2>/dev/null || true
fi

%postun
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications 2>/dev/null || true
fi
echo "OmniScript removed. 'omni' command no longer available."

%files
/usr/bin/omni
/usr/share/doc/omniscript/*
/usr/share/omniscript/examples/*
/usr/share/applications/omniscript.desktop

%changelog
* Sun Sep 21 2026 OmniNodeCo - $VERSION-1
- Super simple rewrite with draw, cmd, pathlib — OS integrated, type 'omni' and reacts

SPEC

  rpmbuild --define "_topdir $RPMBUILD_ROOT" -bb "$RPMBUILD_ROOT/SPECS/omniscript.spec"

  # Find built RPM
  BUILT_RPM=$(find "$RPMBUILD_ROOT/RPMS" -name "*.rpm" | head -n 1)
  if [ -n "$BUILT_RPM" ] && [ -f "$BUILT_RPM" ]; then
    cp "$BUILT_RPM" "$RPM_FILE"
    echo "    RPM created: $RPM_FILE — install then type 'omni' and it reacts"
    ls -lh "$RPM_FILE"
  else
    echo "    rpmbuild did not produce RPM, listing:"
    find "$RPMBUILD_ROOT" -type f | head -n 20
  fi

  rm -rf "$RPMBUILD_ROOT"

else
  echo "    rpmbuild not found, trying to create RPM via tar + rpm spec fallback"
  if command -v alien >/dev/null 2>&1 && [ -f "$DIST_DIR/omniscript_${VERSION}_amd64.deb" ]; then
    echo "    Converting DEB to RPM via alien"
    (cd "$DIST_DIR" && fakeroot alien --to-rpm --scripts "omniscript_${VERSION}_amd64.deb" 2>&1 || alien --to-rpm "omniscript_${VERSION}_amd64.deb" 2>&1) || true
    ls -lh "$DIST_DIR"/*.rpm 2>&1 || true
  else
    echo "    No rpmbuild, creating placeholder tar.gz as RPM fallback"
    echo "    Install rpm-build: sudo apt-get install rpm"
    tar -czf "$DIST_DIR/omniscript-${VERSION}-linux-${RPMARCH}.tar.gz" -C "$ROOT" omni README.md LICENSE VERSION examples/ 2>/dev/null || true
  fi
fi

# Also ensure generic linux tarball exists
TAR_FILE="$DIST_DIR/omniscript-${VERSION}-linux-${RPMARCH}.tar.gz"
if [ ! -f "$TAR_FILE" ]; then
  tar -czf "$TAR_FILE" -C "$ROOT" omni README.md LICENSE VERSION examples/ 2>/dev/null || true
  echo "    Tarball created: $TAR_FILE"
fi

echo "==> Done — after 'sudo rpm -i $RPM_FILE', type 'omni' in terminal and it reacts"
ls -lh "$DIST_DIR" | grep -E "rpm|tar.gz|deb" || true
