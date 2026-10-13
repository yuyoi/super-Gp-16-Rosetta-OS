@echo off
rem One-time: NAM runtime (MIT, Steven Atkinson) into this folder only -- nothing system-wide
py -3.10 -m pip install --no-deps --target "%~dp0_vendor" neural-amp-modeler wavio
mkdir "%~dp0captures" 2>nul
echo Done. Put .nam captures / .wav IRs in the captures folder and start "GP Tone Zone.cmd".
pause
