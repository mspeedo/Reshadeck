#!/bin/bash

FXNAME="$1"
SHADER_DIR="$2"
FORCE="${3:-}"

cleanup_temp_files() {
    local keep="$1"

    # Remove temporary files from the previous generic naming scheme.
    find "$SHADER_DIR" -maxdepth 1 -type f -name 'RESHADCK_*.fx' -delete 2>/dev/null || true

    # Remove old CAS temporary files except the currently active one.
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/CAS_[0-9]{4}[A-Za-z0-9]{4}\.fx" \
        ! -name "$keep" -delete 2>/dev/null || true

    # Remove generic temporary files produced by this version. The format is:
    # <shader-base>_<10-char-content-hash><4-char-random>.fx
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/.+_[0-9a-f]{10}[A-Za-z0-9]{4}\.fx" \
        ! -name "$keep" -delete 2>/dev/null || true
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

    RAND=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 4)
    CURRENTFX=$(DISPLAY=:0 xprop -root GAMESCOPE_RESHADE_EFFECT 2>/dev/null | awk -F'"' '/GAMESCOPE_RESHADE_EFFECT/ {print $2}')

    if [ "$FXNAME" = "CAS.fx" ]; then
        # Preserve the original CAS naming logic exactly:
        # CAS_<contrast><sharpness><4-char-random>.fx
        CONTRAST=$(grep -Po 'uniform\s+float\s+Contrast\s*=\s*\K[-+]?[0-9]+\.[0-9]' "$SOURCE" | head -n1)
        SHARPNESS=$(grep -Po 'uniform\s+float\s+Sharpness\s*=\s*\K[-+]?[0-9]+\.[0-9]' "$SOURCE" | head -n1)
        C_SHORT=$(echo "$CONTRAST" | tr -d '.')
        S_SHORT=$(echo "$SHARPNESS" | tr -d '.')
        SIGNATURE="CAS_${C_SHORT}${S_SHORT}"
        TEMPFX="${SIGNATURE}${RAND}.fx"

        if [ "$FORCE" = "false" ]; then
            [ "${CURRENTFX:0:${#SIGNATURE}}" = "$SIGNATURE" ] && exit 0
        fi
    else
        # Generic shaders use the same naming principle: one deterministic
        # parameter/content signature plus the same single 4-char random suffix.
        SAFE_BASE=$(basename "$FXNAME" .fx | sed 's/[^A-Za-z0-9_-]/_/g')
        HASH=$(sha256sum "$SOURCE" | awk '{print substr($1,1,10)}')
        SIGNATURE="${SAFE_BASE}_${HASH}"
        TEMPFX="${SIGNATURE}${RAND}.fx"

        if [ "$FORCE" = "false" ]; then
            [ "${CURRENTFX:0:${#SIGNATURE}}" = "$SIGNATURE" ] && exit 0
        fi
    fi

    cp "$SOURCE" "$SHADER_DIR/$TEMPFX"
    DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$TEMPFX"
    cleanup_temp_files "$TEMPFX"
fi
