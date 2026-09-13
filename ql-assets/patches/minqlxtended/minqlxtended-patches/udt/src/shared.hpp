// NOTE: relocated verbatim from upstream's
// UDT_DLL/src/apps/shared.hpp (a console-tool header, not top-level
// UDT_DLL/src/), because json_export.cpp unconditionally #includes it even
// though neither of these two externs is ever called from the code paths
// this bridge uses. Content is unmodified; only its location changed.
#pragma once


#include "uberdemotools.h"


extern void CallbackConsoleMessage(s32 logLevel, const char* message);
extern void CallbackConsoleProgress(f32 progress, void* userData);
