#!/bin/bash

FXNAME="$1"
SHADER_DIR="$2"
FORCE="${3:-}"

cleanup_temp_files() {
    local keep="$1"

    # Clean up temporary files from the previous naming schemes.
    find "$SHADER_DIR" -maxdepth 1 -type f -name 'RESHADCK_*.fx' -delete 2>/dev/null || true
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/CAS_[0-9]{4}[A-Za-z0-9]{4}\.fx" -delete 2>/dev/null || true
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/.+_[0-9a-f]{10}[A-Za-z0-9]{4}\.fx" -delete 2>/dev/null || true

    # Current format: <shader-base>_<4-char-random>.fx. Only treat a file as
    # temporary when the corresponding original <shader-base>.fx exists.
    for path in "$SHADER_DIR"/*_????.fx; do
        [ -e "$path" ] || continue
        name=$(basename "$path")
        [ "$name" = "$keep" ] && continue
        base="${name%_????.fx}.fx"
        [ -f "$SHADER_DIR/$base" ] && rm -f "$path"
    done
}

if [ "$FXNAME" = "None" ] || [ -z "$FXNAME" ]; then
    DISPLAY=:0 xprop -root -remove GAMESCOPE_RESHADE_EFFECT
    cleanup_temp_files ""

elif [ -z "$FORCE" ]; then
    # Normal shader selection/toggle. Use the real file name.
    DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$FXNAME"
    cleanup_temp_files ""

else
    SOURCE="$SHADER_DIR/$FXNAME"
    [ -f "$SOURCE" ] || exit 1

    SAFE_BASE=$(basename "$FXNAME" .fx | sed 's/[^A-Za-z0-9_-]/_/g')
    RAND=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 4)
    TEMPFX="${SAFE_BASE}_${RAND}.fx"

    cp "$SOURCE" "$SHADER_DIR/$TEMPFX"
    DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$TEMPFX"
    cleanup_temp_files "$TEMPFX"
fi
