#!/bin/sh
# Wraps the PyInstaller output (dist/Dzinde) into dist/Dzinde-x86_64.AppImage. Run from the repo root on Linux.
set -eu
APPDIR=build/Dzinde.AppDir
rm -rf "$APPDIR" && mkdir -p "$APPDIR/usr/lib"
cp -a dist/Dzinde "$APPDIR/usr/lib/dzinde"
cp packaging/linux/dzinde.desktop "$APPDIR/"
cp packaging/icon.png "$APPDIR/dzinde.png"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/dzinde/Dzinde" "$@"
RUN
chmod +x "$APPDIR/AppRun"
[ -x build/appimagetool ] || curl -fsSL -o build/appimagetool \
  https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x build/appimagetool
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 build/appimagetool "$APPDIR" dist/Dzinde-x86_64.AppImage
