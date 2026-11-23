# QIDI Plus 4: what's known

Notes on QIDI's Plus 4 software, gathered while porting ideas from Valve Oil. They describe what QIDI ships and how one printer behaved; they aren't promises about every Plus 4.

Evidence labels:

- **Runtime-confirmed:** seen on a running printer.
- **Config-confirmed:** in QIDI's update package or stock config.
- **Static-recovered:** found in QIDI's compiled files (names, strings); proves something is there, not how it behaves.
- **Unresolved:** not known yet.


The Plus 4 predates the Max 4 and Plus 5 and runs a different software generation: an MKS host image with the `mks` user, a single `gcode_macro.cfg`, and compiled Box modules built for Python 3.7. QIDI no longer sells it but still publishes updates.

## Firmware packages

- **Config-confirmed (SOC payload `QD_Plus4_SOC`, 17,690,392 bytes, SHA-256 `ef432bd700ef2b93a4f4f76a3975449f2e981d0200c1e3e58e21236d09fc1d47`; touchscreen payload `QD_Plus4_UI`, 20,540,552 bytes, SHA-256 `df71c47d89a513a587a1ce7c50e0ed94af6f4cfc52aa26d4a359abd47a49071c`):** the SOC payload is a Debian binary package, `QIDI-X-Plus4` version `1.0.1`, `arm64`, holding 1,165 files. `/root/xindi/version` in it reads `mcu = V0.12.0`, `ui = V211`, `soc = V2.1.1`. The touchscreen payload is the serial screen's own image, not a host file.
- **Config-confirmed (same payload):** it installs into `/home/mks`, `/root`, and `/usr`. It ships:
  - 23 files under `/home/mks/klipper/klippy` (among them `gcode.py`, `klippy.py`, `webhooks.py`, `heaters.py`, `save_variables.py`, `tmc2209.py`, `tmc2240.py`, `print_stats_manager.py`, and compiled `aht20_f.so`, `box_detect.so`, `box_extras.so`, `box_rfid.so`, `box_stepper.so`, `buttons_irq.so`, `multi_color_controller.so`) and 77 under `/home/mks/moonraker`, with compiled `extensions.so`, `frp_manager.so`, and `mqtt.so` components. The rest of Klipper and Moonraker comes from the factory image, so a full stock tree can only be read from a printer.
  - Fluidd `v1.30.4` in `/home/mks/fluidd`.
  - `printer.cfg` (SHA-256 `2865d9cb…`), `gcode_macro.cfg` (`30d6aa8a…`), `box.cfg`, `box1.cfg`–`box4.cfg`, `moonraker.conf` (CRLF), `officiall_filas_list.cfg`, `filament-0.4.json`, and `saved_variables.cfg.bak` in `printer_data/config`. `plr.cfg`, `time_update.cfg`, `timelapse.cfg`, and `KAMP_Settings.cfg`, which `printer.cfg` includes, are not in the payload.
  - Box templates `/home/mks/cfg_with_0` through `cfg_with_4`, Box MCU firmware `mcu_box_to_v1_1.1.1.bin` with `mcu_update_BOX_to_v1.sh` (`VERSION=1.2.6`, Klipper device `usb-Klipper_QIDI_BOX_V2-*`, STM32 bootloader `usb-*MKS_COLOR*_BOOT*`), and the `serial_com`, `hid-flash`, `json_reader`, and `zlib_decompress` tools.
  - The touchscreen app `/root/xindi/build/xindi`, `/root/QIDILink-client/udp_server`, `/usr/bin/makerbase-automount`, and Wi-Fi modules for kernel `5.16.20-rockchip64` (`aic8800`).
- **Config-confirmed (maintainer scripts):** `preinst` deletes old `mcu_box_to_v1_*.bin` files and the previous Box, `buttons_irq`, and `aht20_f` modules and three Moonraker components, stops and disables `QIDILink-client.service`, and copies `printer.cfg` and `gcode_macro.cfg` to `printer_<date>.cfg` and `gcode_macro_<date>.cfg`. The package then replaces both. When the printer had no `saved_variables.cfg.bak` before the update, `postinst` overwrites `saved_variables.cfg` with the packaged `.bak`. It also sets the config directory to mode 777 owned by `mks`, enables `systemd-timesyncd`, restarts Klipper and Moonraker, and sends `firmware_restart`. A model check against `/dev_info.txt` (`QIDI@x-plus_4`) is present but commented out.

## Firmware 1.8.x

- **Unresolved:** the stock files of 1.8.1 and 1.8.2. QIDI shipped both only through the printer's online update. `QIDITECH/QIDI_PLUS4`'s releases go from `Plus4_v1.7.1` (2025-08-06) to `Plus_v2.1.1`, and the `PLUS4` branches of `QIDITECH/klipper` and `QIDITECH/moonraker` stop at `V1.7.1` (`4bb7c63`) and `v1.7.0` (`6a6d226`). So 1.8.x can only be bracketed by 1.7.1 and V2.1.1.
- **Config-confirmed (`QIDITECH/QIDI_PLUS4` `ec595fc` `config/`, now `stock/plus4-1.7.1/`, against the V2.1.1 payload):**
  - Both versions' `printer.cfg` and `gcode_macro.cfg` start `# QIDI Plus4 V1.0.0`.
  - `printer.cfg` (1.7.1 SHA-256 `ed71c9f9…`) differs only by `[print_stats_manager]` and `[multi_color_controller]`, which V2.1.1 adds before the SAVE_CONFIG block.
  - `gcode_macro.cfg` (`551502f1…`) differs in two places. In `ENABLE_ALL_SENSOR`, 1.7.1 runs `CLEAR_MOTION_DATA` and then `SET_FILAMENT_SENSOR SENSOR=box_motion_sensor ENABLE=1`, where V2.1.1 runs `CLEAR_MOTION_DATA SENSOR=box_motion_sensor`. `[gcode_arcs]` `resolution` goes from 0.5 to 1.0.
  - The Box files: `rotation_distance` 13.4 becomes 13.6, `step_pulse_duration:0.000000100` is added to each slot, and `is_box_heter` is corrected to `is_box_heater`.
  - Every Plus4 Grease edit finds its stock text once in 1.7.1, as in V2.1.1 (`tests/test_grease.py`, `OlderStockTests`).
- **Config-confirmed (`officiall_filas_list.cfg`, same comparison):** no filament ID's `box_max_temp` changed. V2.1.1 renames some (`fila1` PLA to PLA Rapido, `fila11` ABS to ABS Rapido, `fila41` PETG to PETG Rapido, `fila50` TPU to TPU 95A-HF; `fila25` PA12-CF becomes PA6-CF and PA12-CF moves to `fila27`, both 65), fills empty IDs 10, 15, 20, 23, 27, 35, 36, 42, 43, 46 and 48, and gives `fila8` PLA Matte Basic a `box_max_temp` of 0 where 1.7.1 left it blank.
- **Static-recovered (`QIDITECH/klipper` `PLUS4` `4bb7c63` against the V2.1.1 payload's 23 klippy files):**
  - The same in both: `aht20_f.so`, `box_detect.so`, `box_rfid.so`, `box_heater_fan.py`, `heaters.py`, `hall_filament_width_sensor.py`, `tmc2209.py`, `tmc2240.py`, `temperature_sensors.cfg`, `heater_bed.py` and `klippy.py`.
  - Different: `box_extras.so`, `box_stepper.so`, `save_variables.py`, `gcode.py`, `webhooks.py`, `filament_motion_sensor.py`, `chamber_fan.py`, `gcode_arcs.py` and `verify_heater.py`.
  - New in V2.1.1: `multi_color_controller.so`, `print_stats_manager.py` and `buttons_irq.so` (1.7.1 has `buttons_irq.py`).
  - V2.1.1's `box_extras.so` names the per-Box status (`boxes`, `aht20_humidity`, `aht20_temp`, `box_target_temp`, `dry_state`, `filament_info`, `loaded_slot`, `slot16`) and `box_adapter`; 1.7.1's names none of them. Both name `E_LOAD`, `E_UNLOAD`, `E_BOX`, `RFID_READ`, `ENABLE_BOX_DRY`, `DISABLE_BOX_DRY`, `BOX_SELF_INSPECTION`, `TRY_MOVE_AGAIN` and `runout_button`; `INIT_MAPPING_VALUE` is new.
  - V2.1.1's `multi_color_controller.so` holds a first-generation adapter ("一代适配器 - 直接控制现有Klipper组件", driving the existing Klipper objects) and a remote-mode adapter for the second-generation Box.
- **Runtime-confirmed (operator klippy logs, July and August 2026, Plus 4s on 1.8.1 and 1.8.2):** QIDI's multi-color controller (`多色控制器`) started in local mode (`本地模式适配器连接成功`), looked up `box_extras` (one restart logged `Unknown config object 'box_extras'`), and threw `'ToolChange' object has no attribute 'is_tool_change'` on every status update. A Beacon-converted 1.8.1 printer's config already had `[print_stats_manager]`, `[multi_color_controller]` and V2.1.1's form of `ENABLE_ALL_SENSOR`. Neither the local-mode text nor that error is in V2.1.1's build. So 1.8.x has the multi-color controller design in an earlier build than V2.1.1's. Whether its `box_extras` publishes the per-Box status is unresolved.
- **Static-recovered (Moonraker):** `QIDITECH/moonraker` `PLUS4` `v1.7.0` and the V2.1.1 payload both report `API_VERSION` (1, 4, 0); V2.1.1 changes 24 of the files and adds 8, QIDI's `extensions`, `frp_manager` and `mqtt` components among them. Fluidd v1.38.1's minimum is `v0.8.0-309`, and an older Moonraker only gets a warning.
- **Runtime-confirmed (operator output, 2026-11-22, a stock Plus 4 on V1.8.2 with two Boxes and the owner's own additions):** `install --dry-run` listed every standard change `available`. `tools/config_diff.py` against the V2.1.1 payload found no stock differences in `printer.cfg` (V2.1.1's `[print_stats_manager]` and `[multi_color_controller]` are already there), `gcode_macro.cfg` (V2.1.1's `ENABLE_ALL_SENSOR` and `[gcode_arcs]` text), `box1.cfg` to `box4.cfg`, or any `[filaN]` entry of `officiall_filas_list.cfg`. Everything it listed was the owner's: Spoolman includes and macros, a `BOX_SLOT_MOVE` macro, bed meshes and input shaper results, four `[vendor_list]` names, and `moonraker.conf`'s `[database]`, `[spoolman]` and a narrower `trusted_clients`. So for the files Plus4 Grease edits, 1.8.2's stock text is V2.1.1's. 1.8.1's isn't seen directly; the 1.8.1 config above already had V2.1.1's text. `klipper_report.py` showed `mcu_box1` and `mcu_box2` (stm32f401xc), and the Box boards' task load (`mcu_task_avg` + 3 × `mcu_task_stddev` against 2.5 ms) up to 63% and 68% at idle, in the two minutes the log then held; during a 34-minute print the next day it peaked at 21% and 22%. What raised it at idle is unresolved.
- **What Plus4 Grease does with this:** it accepts 1.8.1 and 1.8.2, and says they're untested when it runs on them. Its config edits, `--box-dry` and the Box card's commands only use what 1.7.1 already had. The Box card falls back to `save_variables` and the filament list where V2.1.1's per-Box status is missing; drying started from the touchscreen is only shown from that status.

## Klipper and stock configuration

- **Config-confirmed (`2.1.1`):** `printer.cfg` includes, in order, `plr.cfg`, `gcode_macro.cfg`, `time_update.cfg`, `timelapse.cfg`, `KAMP_Settings.cfg`, and `box.cfg`. There is no `klipper-macros-qd/` directory: `gcode_macro.cfg` holds `homing_override`, `PRINT_START`, `PRINT_END`, `CANCEL_PRINT`, `PAUSE`, `RESUME`, the probe and Z-offset macros (`_CG28`, `Z_VIBRATE`, `set_zoffset`, `move_subzoffset`), `CLEAR_NOZZLE`, `MOVE_TO_TRASH`, `EXTRUSION_AND_FLUSH`, and the `M` code overrides. `box1.cfg` holds `T0`–`T15` and `UNLOAD_T0`–`UNLOAD_T15`. None of the Max 4 and Plus 5 `klipper-macros-qd` internals (`_km_globals`, `_print_start_phase_*`, `_HOME_X`, `CUT_FILAMENT_1`) exist.
- **Config-confirmed:** `[mcu]` is `/dev/ttyS2` and the toolhead `[mcu U_1]` is `/dev/ttyS0`; no serial number is recorded. X/Y are TMC2240 with sensorless homing (`homing_retract_dist: 0`), X −1.5–307 and Y −2–325. Z is two TMC2209 lead screws (`stepper_z`, `stepper_z1`, 128 microsteps, `rotation_distance` 4) with `[z_tilt]`, homed down on the `smart_effector` probe with a sensorless Z-max endstop (`endstop_pin_reverse`, 285 mm). `[printer]` is `max_velocity` 600, `max_accel` 20000, `square_corner_velocity` 8. The probe is `[smart_effector]` with `[qdprobe]`; `[z_tilt]` and `[bed_mesh]` travel at 150 mm/s. Other sections include `hall_filament_width_sensor`, `heater_generic chamber`, three `heater_fan` hotend fans, `chamber_fan`, `controller_fan board_fan`, `print_stats_manager`, and `multi_color_controller`.
- **Config-confirmed:** stock `PRINT_START` homes, then waits for the bed (`M190`) before `Z_TILT_ADJUST` and `G29`, and only then heats the hotend (`M109`). With a Box it clears 16 `runout_N` variables with a `G4 P100` after each, 1.6 s of fixed dead time.
- **Config-confirmed:** the payload's `box_stepper.so` (SHA-256 `5de15644d3af91b7cf9afa25a68f73b95e98f3ae6a66a6690f9e5f73f583a1c7`) is not one of `tltg_box_feed_motion`'s known builds, so that module would stay inactive on a Plus 4. `box_extras.so` is `c563d135…` and `multi_color_controller.so` `f572e26d…`. All the compiled modules were built with `GCC (Debian 8.3.0-6) 8.3.0`, Debian 10's compiler.
- **Config-confirmed:** `klippy-env` is Python 3.7.
- **Static-recovered (strings of the `2.1.1` touchscreen app `/root/xindi/build/xindi`):** the app builds those rules itself: `sudo iptables -A INPUT -i …/24 -j ACCEPT`, `… ! -s …/24 -j DROP`, the same for `FORWARD`, and `sudo iptables -F` to clear them, beside its LAN-mode settings (`general.lan_mode`, `general.lan_mode_live`, `saveLanmodeConfig`) and the `app_connection` method it shares with `config.mksini`. So the Plus 4's LAN-only mode is a firewall that cuts the printer off from the internet, not just from QIDI's cloud.
- **Static-recovered (2026-11-20, strings of the `2.1.1` payload's compiled modules):** the Plus 4's Box code names the same flow objects as the Max 4 and Plus 5 builds. `multi_color_controller.so` has `task_queue_manager`, `current_task`, `current_step`, `is_cancelled`, `box_adapter`, `operation_adapter`, `method_map`, `start_flow`, `FLOW_MAP`, `target_load_slot`, `target_unload_slot`, `set_filament_information`, `get_filament_info_by_id`, `get_max_temp_id`, `material_db`, and `fila_json`. `get_value_by_key` is in `box_extras.so`, `box_stepper.so`, and `box_detect.so`, `next_cmd_time` in `box_stepper.so`, and `fm17550_read_card` and `read_rfid_timer` in `box_rfid.so`. `_pause_print_retry_flow`, which `tltg_box_flow_recovery` looks up with a default, is in none of them. Names prove presence, not behavior.
- **Static-recovered (2026-11-20, `QIDITECH/klipper` `PLUS4` `4bb7c63` (`V1.7.1`) with the `2.1.1` payload's 23 files laid over it):** `extras/probe.py` predates upstream's probe rework: it has `PrinterProbe`, `ProbeEndstopWrapper`, and `ProbePointsHelper`, but no `ProbeSessionHelper` or `calc_probe_z_average`. `extras/stepper_enable.py` has no `ENABLE_DELAY_TIME`. There is no `box485_multicolor.py` or `box_protocol.py`. The MCUs are `mcu` and `U_1`; there is no `THR`. Whether a `2.1.1` printer's tree matches this assembly is unconfirmed: an earlier update may have changed files the `2.1.1` payload doesn't ship.

## Runtime

- **Runtime-confirmed (operator report, 2026-11-20, one Plus 4 on `2.1.1` with a Beacon probe conversion, without Valve Oil):** Debian GNU/Linux 10 (buster), system `python3` 3.7.3, glibc 2.28, `aarch64`. `/` is `/dev/mmcblk1p2`, 28 GB with 21 GB free, and `/home` is on it. `mks` needs a password for `sudo`. `/root` is mode 700, so `mks` can't read `/root/xindi/version`. `curl` and `wget` are installed. The printer could not resolve `raw.githubusercontent.com`.
- **Runtime-confirmed (`tools/collect_plus4.py`, 2026-11-21, same printer):**
  - Host: Armbian 22.05.0-trunk, kernel `5.16.20-rockchip64 #trunk SMP PREEMPT Mon Jul 25 01:58:45 UTC 2022`. Device tree model `Makerbase mks-pi`, compatible `firefly,roc-rk3328-cc rockchip,rk3328`: four Cortex-A53 cores (part `0xd03`) and 976 MB of memory. Armbian's own zram swap is on, 488 MB (`armbian-zram-config.service`, `zram-setup@zram0.service`).
  - Model: `/dev_info.txt` is readable by `mks` and reads `QIDI@x-plus_4` with no trailing newline, the value QIDI's commented-out `preinst` check expects.
  - Network: `/etc/resolv.conf` lists only public resolvers, `1.1.1.1`, `8.8.8.8`, and `223.6.6.6`. `/etc/hosts` pins `github.com` (`140.82.113.3`), `gist.github.com`, and `assets-cdn.github.com`, so `github.com` resolved while every other name timed out. The default route was the LAN router, which answered pings; nothing beyond it answered, not even a TCP connection to a GitHub address given directly.
  - Firewall: `iptables` held, twice over, `INPUT` and `FORWARD` rules accepting `eth0` traffic from `192.168.1.0/24` and dropping the rest, and loopback traffic from outside `127.0.0.0/24`, with no rule for established connections. Replies from the internet were dropped, which explains the network results, and so was the printer's own connection to its LAN address over loopback.
  - Turning LAN mode off on the touchscreen restored internet access: afterwards `curl https://1.1.1.1` got `HTTP/2 301`.
  - Box: with the Box detected, Klipper logged `Material config not found at /home/qidi/printer_data/config/officiall_filas_list.cfg` at startup. The Plus 4's Box code looks for QIDI's filament list under the Max 4 and Plus 5 home, `/home/qidi`, while the Plus 4 keeps it in `/home/mks`. The Box's USB name is `usb-Klipper_QIDI_BOX_V1_1.1.1_…`, and Klipper reported `mcu_box1` as `KLP_MCU_MKS_V1_1.1.1`, an `stm32f401xc`.
  - Valve Oil's development Box tracer (`scripts/box_trace/dev_box_trace.py` in its repository): in each of three starts with it loaded, Klipper configured all four MCUs (`mcu`, `mcu_box1`, `U_1`, `beacon`) and then stopped: no `Stats` line, no ready, no error, until the printer was power-cycled. The tracer's log held only its start line, so the stall came inside its ready handler before its first object line, while it read every attribute of the first Box object. Without the tracer, Klipper started normally. Which attribute read blocks is unresolved.
  - Firmware identity: `/root/xindi/version` (read with `sudo`) matches the payload's. `dpkg-query` lists no `QIDI-X-Plus4` package, so the update doesn't leave its package registered, and the `dpkg` database can't identify a Plus 4.
  - Services running or active include `klipper`, `klipper_mcu`, `moonraker`, `nginx`, `makerbase-client`, `QIDILink-client`, `cups`, `unattended-upgrades`, `hostapd`, `ipsec`, `xl2tpd`, `tuning`, `cpufrequtils`, `dhcpcd`, `network-manager`, `wpa_supplicant`, and `systemd-timesyncd`.
  - Klipper: `git describe` is `v0.12.0-65-g96ab9069-dirty`, and Moonraker reports `software_version` the same. 190 of the 199 `klippy` files match the assembled `PLUS4` + `2.1.1` tree. `mcu.py`, `stepper.py`, and `extras/bed_mesh.py`, `gcode_macro_break.py`, `gcode_move.py`, `probe.py`, `qdprobe.py`, `resonance_tester.py`, and `shaper_calibrate.py` match neither it nor any version in `QIDITECH/klipper` `PLUS4` history; whether QIDI's unpublished updates or this printer's changes made them is unknown. `extras/beacon.py` is a link into `/home/mks/beacon_klipper`, from the Beacon conversion.
  - Moonraker: `v0.8.0-379-g346a3d7-dirty`, API `1.4.0`. All 77 Moonraker files in the payload are on the printer unchanged, among 154.
  - Fluidd: `v1.30.4`, as in the payload.
  - Box: `cfg_with_0`–`cfg_with_4` are byte-identical to the payload's, so a `2.1.1` update replaces any edits to them. `box.cfg` was the no-Box form, with every `boxN.cfg` include commented out.
  - Factory config not in the payload: `plr.cfg` (66 lines, `gcode_shell_command` entries for `/home/mks/scripts/plr/`), `time_update.cfg`, `timelapse.cfg`, `KAMP_Settings.cfg`, and `KAMP/` (`Adaptive_Meshing.cfg`, `Line_Purge.cfg`, `1Line_Purge.cfg`, `Smart_Park.cfg`, `Voron_Purge.cfg`, `KAMP_Settings.cfg`). None matches a file in `QIDITECH/QIDI_PLUS4` history, and this printer's KAMP files were edited before, so they are not a stock baseline.

## Unresolved

- Whether every Plus 4 has `/dev_info.txt` with `QIDI@x-plus_4`, and what QIDI's other MKS-based printers write there.
- Stock `plr.cfg`, `time_update.cfg`, `timelapse.cfg`, `KAMP_Settings.cfg`, and `KAMP/`, and the stock versions of the nine `klippy` files above.
- Which screen holds the Plus 4's LAN mode switch, whether turning it off left `iptables` empty, and whether the rules come back at boot while it's off.
- How the Plus 4's compiled Box modules differ from the Max 4 and Plus 5 builds in the methods Valve Oil's Box modules wrap.
- Whether Valve Oil's Klipper extras, which parse under Python 3.7, run against QIDI's Plus 4 Klipper.
- Main-loop load and memory while printing.


## QIDI Box on USB (seen on a Plus 4 with one Box, 2026-11-21)

- The Box has its own USB hub (`1a40:0801`, "USB 2.0 Hub") with the Box board behind it, and both run on the Box's own power: switching the Box off removes the board, then the hub.
- Every time the Box board starts, it first shows up as MKS's bootloader (`0483:5740`, "MKS COLOR BOOT") for about 2.5 s, then disconnects and comes back as Klipper firmware (`1d50:614e`, "Klipper QIDI_BOX_V1_1.1.1"). Seen from the mainboard, a Box start is two connects with a disconnect between them.
- A household power flicker rebooted the Box (gone about 2 s, then its bootloader, then Klipper) while the printer stayed up. One earlier "Lost communication with MCU 'mcu_box1'" matches the same thing. The printer's supply rides through flickers the Box's doesn't.
- QIDI's Plus 4 Klipper has a compiled `box_detect` module; switching the Box off while idle logged no Klipper shutdown.

## Boards (from QIDI's 2.1.1 `printer.cfg` and a Plus 4's `klippy.log`)

There is no separate single-board computer. The mainboard carries both processors:

- **Linux processor:** a Rockchip RK3328 (four Cortex-A53 cores, 1 GB RAM, eMMC), on Makerbase's MKS PI design (hence the hostname `mkspi` and user `mks`). It runs Armbian, Klipper's host software (klippy), Moonraker, Fluidd, and QIDI's touchscreen app `xindi`.
- **`U_1`, STM32F401 at 84 MHz:** on the mainboard, on the RK3328's `/dev/ttyS0` at 500000 baud. Drives X, Y, both Z motors, the bed and chamber heaters, the chamber and auxiliary fans, and reads QIDI's probe (`smart_effector` on `U_1:PC1`).
- **`mcu`, STM32F103 at 72 MHz:** the toolhead board, on `/dev/ttyS2` at 500000 baud. Drives the extruder motor and heater, the part cooling fan and the hotend fans.
- **USB:** the QIDI Box (its own STM32F401 behind its own hub) and, on a conversion, a Beacon.

## Spool tags (RFID)

- Each Box has two FM17550 RFID readers, each serving two neighbouring slots, run by the Box's own firmware (`QIDI_BOX_V1_1.1.1` on V2.1.1; QIDI's update carries it as `/home/mks/mcu_box_to_v1_1.1.1.bin`). Klipper's side is QIDI's compiled `box_rfid.so`: it configures each reader with `config_fm17550 oid=%d spi_oid=%d`, asks for a read with `fm17550_read_card`, and gets back `fm17550_read_card_return oid=%c status=%c data=%*s`, which it decodes as QIDI's tag format (or reports `did not recognize the filament`). Nothing on the printer side can make the reader do anything else.
- QIDI's tag format is public ([QIDI wiki](https://wiki.qidi3d.com/en/QIDIBOX/RFID)): a MIFARE Classic 1K tag with QIDI's material, color and vendor codes in sector 1, block 0 (data block 4). Blank MIFARE Classic tags written in that format with a phone or a tag writer read on the Box like QIDI's own spools. SimplyPrint, NFC-Spool (Android), QBox NFC Tagger and others write them.
- Valve Oil makes the Box read Bambu Lab, Anycubic, Elegoo, Creality, TigerTag and OpenTag3D tags with its own Box firmware, built from QIDI's USB Box firmware `02.03.01.21` for the Max 4, Plus 5 and Smart 5: it adds two raw reader commands (`fm17550_select`, `fm17550_transceive`) in place of four unused QIDI test commands, and a Klipper module decodes each brand's format. Its flasher only accepts that exact QIDI image (by hash). The Plus 4's Box runs QIDI's `V1_1.1.1` firmware with QIDI's older host modules, so porting it would mean the same patch made for that firmware, and checked as carefully, before flashing a Box.
- Without tags, a slot's filament can be set by hand: the touchscreen, QIDI's page, or Edit filament on Plus4 Grease's Fluidd, all save `filament_slotN`, `vendor_slotN` and `color_slotN`.

## Box commands QIDI's touchscreen sends (V2.1.1)

From [qbdisplay](https://github.com/CharlyBrownFR/qbdisplay-plus4) (CharlyBrownFR, GPL-3.0), which recorded what QIDI's display program (`makerbase-client`, "xindi") sends, and checked against the command names in QIDI's `box_extras.so`:

| What | Command |
|---|---|
| Load, unload, eject a slot | `E_LOAD SLOT=<n>`, `E_UNLOAD SLOT=<n>`, `E_BOX SLOT=<n>` (QIDI's Fluidd sends `slot=<n>`; Klipper reads either); the external spool is slot 16 |
| Read a slot's tag | `RFID_READ SLOT=slot<n>` |
| Dry Box 1 | `ENABLE_BOX_DRY BOX=1 TEMP=<°C> END_TIME=<hours>`, stopped with `DISABLE_BOX_DRY BOX=1`; `box_extras` reports `dry_state` and `end_time` |
| Retry a failed Box step | `TRY_MOVE_AGAIN` |
| Box self-check | `BOX_SELF_INSPECTION` |
| Automatic reload on/off | `SAVE_VARIABLE VARIABLE=auto_reload_detect VALUE=<0/1>` |

`box_extras.boxes[b]` also has `box_inserted_<i>` and `filament_inserted_<i>` for each slot, and the Box's AHT20 readings. Without a Box (unplugged), QIDI comments the Box out of `box.cfg` and restarts Klipper; `box_extras` is then gone and the external spool is in `multi_color_controller.extra.filament_info`.

QIDI's display file (`800_480.tft`) is flashed by copying a new one to `/root/800_480.tft` and restarting `makerbase-client`, which loads it onto the screen and deletes it when done; QIDI keeps the previous one as `/root/800_480.tft.bak`.
