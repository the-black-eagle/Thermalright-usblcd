#!/bin/bash
set -e

echo "== Installing Python GUI (renamed) + driver =="

CURDIR=$(pwd)
OBJDIR=$(find "$CURDIR" -maxdepth 1 -type d -name 'obj-*' | head -n1)

if [[ -z "$OBJDIR" ]]; then
    echo "ERROR: no build directory found" >&2
    exit 1
fi

echo "Detected OBJDIR=$OBJDIR"

# 1. Install Python GUI renamed to tr-driver (no .py)
install -D -m 0755 "$CURDIR/python/gui_controller.py" \
    "$CURDIR/debian/tr-driver/usr/lib/tr-driver/tr-driver"

# 1a. Also install background_selector.py (new dependency)
install -D -m 0644 "$CURDIR/python/background_selector.py" \
    "$CURDIR/debian/tr-driver/usr/lib/tr-driver/background_selector.py"

# 2. Install compiled .so to Python dist-packages
SOFILE=$(ls "$OBJDIR"/lcd_driver*.so 2>/dev/null | head -n1)
if [[ -z "$SOFILE" ]]; then
    echo "ERROR: lcd_driver .so not found in $OBJDIR" >&2
    exit 1
fi

echo "Found .so: $SOFILE"
install -D -m 0644 "$SOFILE" \
    "$CURDIR/debian/tr-driver/usr/lib/python3/dist-packages/$(basename "$SOFILE")"

# 3. Launcher script
mkdir -p "$CURDIR/debian/tr-driver/usr/bin"
cat >"$CURDIR/debian/tr-driver/usr/bin/tr-driver" <<'EOF'
#!/bin/sh
exec python3 /usr/lib/tr-driver/tr-driver "$@"
EOF
chmod 0755 "$CURDIR/debian/tr-driver/usr/bin/tr-driver"

# 4. Icon and desktop
install -D -m 0644 "$CURDIR/tr-driver.png" \
    "$CURDIR/debian/tr-driver/usr/share/icons/hicolor/256x256/apps/tr-driver.png"

install -D -m 0644 "$CURDIR/tr-driver.desktop" \
    "$CURDIR/debian/tr-driver/usr/share/applications/tr-driver.desktop"

echo "✅ Install complete."
