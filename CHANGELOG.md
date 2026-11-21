# Changelog

## 0.1.0
- First release, for the QIDI Plus 4 on firmware V2.1.1.
- Installer with `install`, `install --dry-run`, `status`, and `uninstall`. It checks the printer is a Plus 4 on V2.1.1, backs up every file it changes, restarts Klipper, and puts everything back if Klipper doesn't come back ready.
- Print start no longer waits 1.6 s while clearing the Box runout flags.
- A new bed mesh is saved after 0.5 s instead of 5 s.
