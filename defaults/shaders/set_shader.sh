#!/bin/bash

FXNAME="$1"
SHADER_DIR="$2"

if [ "$FXNAME" = "None" ] || [ -z "$FXNAME" ]; then
    DISPLAY=:0 xprop -root -remove GAMESCOPE_RESHADE_EFFECT

elif [ "$FXNAME" = "CAS.fx" ]; then
    # Extract integer + first decimal, no rounding
    CONTRAST=$(grep -Po 'uniform\s+float\s+Contrast\s*=\s*\K[-+]?[0-9]+\.[0-9]' "$SHADER_DIR/CAS.fx" | head -n1)
    SHARPNESS=$(grep -Po 'uniform\s+float\s+Sharpness\s*=\s*\K[-+]?[0-9]+\.[0-9]' "$SHADER_DIR/CAS.fx" | head -n1)
    # Remove decimal dot
    C_SHORT=$(echo "$CONTRAST" | tr -d '.')
    S_SHORT=$(echo "$SHARPNESS" | tr -d '.')
    RAND=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 4)
    TEMPFX="CAS_${C_SHORT}${S_SHORT}${RAND}.fx"
    cp "$SHADER_DIR/CAS.fx" "$SHADER_DIR/$TEMPFX"
    DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$TEMPFX"
    # Delete all other CAS_########.fx (8 chars after CAS_)
    find "$SHADER_DIR" -maxdepth 1 -type f -regextype posix-extended \
        -regex ".*/CAS_[0-9]{4}[A-Za-z0-9]{4}\.fx" ! -name "$TEMPFX" -exec rm {} \;

else
    DISPLAY=:0 xprop -root -f GAMESCOPE_RESHADE_EFFECT 8u -set GAMESCOPE_RESHADE_EFFECT "$FXNAME"
fi
