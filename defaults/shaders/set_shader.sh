#!/bin/bash

FXNAME="$1"
SHADER_DIR="$2"
FORCE="${3:-}"
SOURCE_OVERRIDE="${4:-}"

cleanup_temp_files() {
    local keep="$1"

    # Clean up temporary files from previous naming schemes.
    find "$SHADER_DIR" -maxdepth 1 -type f -name 'RESHADCK_*.fx' -delete 2>/dev/null || true
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/CAS_[0-9]{4}[A-Za-z0-9]{4}\.fx" -delete 2>/dev/null || true
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/.+_[0-9a-f]{10}[A-Za-z0-9]{4}\.fx" -delete 2>/dev/null || true

    # Current format: <shader-base>_<4-char-random>.fx.
    # Deliberately use the simple naming convention requested by Reshadeck.
    for path in "$SHADER_DIR"/*_????.fx; do
        [ -e "$path" ] || continue
        name=$(basename "$path")
        [ "$name" = "$keep" ] && continue
        base="${name%_????.fx}.fx"
        [ -f "$SHADER_DIR/$base" ] && rm -f "$path"
    done
}

if [ "$FXNAME" = "None" ] || [ -z "$FXNAME" ]; then
    DISPLAY=:0 xprop -root -remove GAMESCOPE_RESHADE_EFFECT >/dev/null 2>&1 || true
    cleanup_temp_files ""
    exit 0
fi

ORIGINAL="$SHADER_DIR/$FXNAME"
if [ ! -f "$ORIGINAL" ]; then
    echo "Shader source does not exist: $ORIGINAL" >&2
    exit 2
fi

if [ -z "$FORCE" ]; then
    # Normal shader selection: point Gamescope directly at the original.
    # Only remove old temp files after xprop succeeds.
    if ! DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u \
        -set GAMESCOPE_RESHADE_EFFECT "$FXNAME"; then
        echo "Failed to set GAMESCOPE_RESHADE_EFFECT to $FXNAME" >&2
        exit 3
    fi
    cleanup_temp_files ""
    exit 0
fi

SOURCE="$ORIGINAL"
if [ -n "$SOURCE_OVERRIDE" ]; then
    SOURCE="$SOURCE_OVERRIDE"
fi
if [ ! -f "$SOURCE" ]; then
    echo "Prepared shader source does not exist: $SOURCE" >&2
    exit 4
fi

BASE="${FXNAME%.fx}"
RAND=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 4)
if [ "${#RAND}" -ne 4 ]; then
    echo "Failed to generate temporary shader suffix" >&2
    exit 5
fi

TEMPFX="${BASE}_${RAND}.fx"
TEMPPATH="$SHADER_DIR/$TEMPFX"

if ! cp "$SOURCE" "$TEMPPATH"; then
    echo "Failed to create temporary shader $TEMPPATH" >&2
    exit 6
fi

if ! DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u \
    -set GAMESCOPE_RESHADE_EFFECT "$TEMPFX"; then
    rm -f "$TEMPPATH"
    echo "Failed to activate temporary shader $TEMPFX" >&2
    exit 7
fi

# The new effect is active. It is now safe to delete older temp copies.
cleanup_temp_files "$TEMPFX"
exit 0
