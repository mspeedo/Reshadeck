#!/bin/bash

FXNAME="$1"
SHADER_DIR="$2"
FORCE="${3:-}"

cleanup_reshadeck_temps() {
    local keep="$1"
    find "$SHADER_DIR" -maxdepth 1 -type f -name 'RESHADCK_*.fx' \
        ! -name "$keep" -delete 2>/dev/null || true

    # Clean up temporary files produced by the old CAS-only reload mechanism.
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/CAS_[0-9]{4}[A-Za-z0-9]{4}\.fx" -delete 2>/dev/null || true
}

if [ "$FXNAME" = "None" ] || [ -z "$FXNAME" ]; then
    DISPLAY=:0 xprop -root -remove GAMESCOPE_RESHADE_EFFECT
    cleanup_reshadeck_temps ""

elif [ -z "$FORCE" ]; then
    # Normal shader selection/toggle. Use the real file name.
    DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$FXNAME"
    cleanup_reshadeck_temps ""

else
    SOURCE="$SHADER_DIR/$FXNAME"
    [ -f "$SOURCE" ] || exit 1

    # Gamescope only notices a shader edit reliably when the effect property
    # changes. Use a content-derived temporary name for all shaders, not just CAS.
    SAFE_BASE=$(basename "$FXNAME" .fx | sed 's/[^A-Za-z0-9_-]/_/g')
    HASH=$(sha256sum "$SOURCE" | awk '{print substr($1,1,10)}')

    if [ "$FORCE" = "true" ]; then
        # Explicit Apply should reload even when shader contents did not change.
        NONCE=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 4)
        TEMPFX="RESHADCK_${SAFE_BASE}_${HASH}_${NONCE}.fx"
    else
        # Automatic parameter updates only need a new name when contents changed.
        TEMPFX="RESHADCK_${SAFE_BASE}_${HASH}.fx"
        CURRENTFX=$(DISPLAY=:0 xprop -root GAMESCOPE_RESHADE_EFFECT 2>/dev/null | awk -F'"' '/GAMESCOPE_RESHADE_EFFECT/ {print $2}')
        [ "$CURRENTFX" = "$TEMPFX" ] && exit 0
    fi

    cp "$SOURCE" "$SHADER_DIR/$TEMPFX"
    DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$TEMPFX"
    cleanup_reshadeck_temps "$TEMPFX"
fi
