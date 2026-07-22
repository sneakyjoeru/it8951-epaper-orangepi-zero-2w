# IT8951 E-Paper Display Driver — Orange Pi Zero 2W

Python driver and HTTP API for the **Waveshare 7.8" E-Ink HAT** (1872×1404, IT8951 controller)
on an **Orange Pi Zero 2W** (Allwinner H616, 1.5GB RAM).

## Features

- 📺 **Full IT8951 SPI driver** — device init, VCOM read/set, 4bpp grayscale display
- 📝 **Antialiased text rendering** — auto-fitting, multi-line, configurable font/size
- 🖼️ **Image display** — auto-scaled to fit screen, aspect ratio preserved, centered
- 🌐 **HTTP API server** — push text/images from any device on the network
- 🎨 **Built-in patterns** — gradient, checkerboard, cross, quarter fill
- 🔄 **Global color inversion** — compensates for hardware color inversion

## Hardware Setup

### What you need

| Component | Details |
|-----------|---------|
| Board | Orange Pi Zero 2W (H616, 1.5GB) |
| Display | Waveshare 7.8" E-Ink HAT (1872×1404, IT8951, SPI) |
| OS | Ubuntu 24.04 LTS (aarch64) |
| Connection | HAT plugs onto GPIO header (SPI mode, not I80) |

### GPIO Pin Mapping (H616, port PH)

| Signal | GPIO | Pin Name | Notes |
|--------|------|----------|-------|
| RST | 226 | PH2 | Reset |
| CS | 229 | PH5 | SPI1 CS0 (manually driven) |
| BUSY | 228 | PH4 | Busy/ready signal |
| SPI CLK | 231 | PH7 | SPI1 clock |
| SPI MOSI | 232 | PH8 | SPI1 data out |
| SPI MISO | 233 | PH9 | SPI1 data in |

### Boot Overlay Configuration

Edit `/boot/orangepiEnv.txt` and set the overlay to **`spi1-cs1-spidev`**:

```ini
overlay_prefix=sun50i-h616
overlays=spi1-cs1-spidev
```

> **Why `spi1-cs1-spidev`?** The Waveshare HAT's CS line is physically wired to
> SPI1 CS0 (GPIO 229). We need to control CS manually (like the Waveshare C code
> does), so we must prevent the kernel from claiming GPIO 229. By enabling only
> CS1 in the overlay, GPIO 229 stays free for manual GPIO control. We open
> `/dev/spidev1.1` (CS1) just to get an SPI file descriptor, then drive CS via
> GPIO 229 ourselves.

After changing the overlay:
```bash
sudo reboot
```

Verify after reboot:
```bash
ls /dev/spidev*    # should show /dev/spidev1.1 only
```

## Installation

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3-pil python3-libgpiod python3-spidev python3-pip
```

### 2. Clone or copy the repository

```bash
sudo mkdir -p /opt/it8951-epaper
sudo cp -r . /opt/it8951-epaper/
```

### 3. Test the driver

```bash
cd /opt/it8951-epaper
sudo python3 main.py --info
```

Expected output:
```
Panel:   1872 x 1404
Memory:  0x00124850
FW:      v.0.1
LUT:     M814T
A2 mode: 6
VCOM:    2500 (=-2.50V)
```

### 4. (Optional) Install as systemd service

```bash
sudo cp it8951-epaper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now it8951-epaper
```

The API server will start on port 8888 and survive reboots.

## Usage — CLI

All commands require `sudo` (for SPI/GPIO access):

```bash
# Show device info + VCOM
sudo python3 main.py --info

# Clear screen to white
sudo python3 main.py --clear

# Display text (auto-fitted, antialiased)
sudo python3 main.py --text "Hello, World!"
sudo python3 main.py --text "Large Text" --font-size 120

# Display image (auto-scaled, aspect preserved, centered)
sudo python3 main.py --image photo.png

# Built-in test patterns
sudo python3 main.py --gradient              # white→black vertical gradient
sudo python3 main.py --checker 50            # 50px checkerboard
sudo python3 main.py --cross 9               # 9px gradient cross (corners→center)
sudo python3 main.py --cross 9 --vertical    # cross with bottom-to-top gradient
sudo python3 main.py --cross 9 --invert      # inverted: black bg, white cross
sudo python3 main.py --quarter               # top-left quarter black
```

## Usage — HTTP API

Start the server:
```bash
sudo python3 main.py --server --port 8888
```

### Endpoints

#### `GET /info`
Returns device info (panel size, firmware, VCOM).

```bash
curl http://192.168.0.199:8888/info
```

#### `POST /text`
Display antialiased text.

```bash
curl -X POST http://192.168.0.199:8888/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from the network!", "font_size": 64}'
```

#### `POST /image`
Display an image (auto-scaled, aspect ratio preserved).

```bash
curl -X POST http://192.168.0.199:8888/image \
  -F "file=@photo.jpg"
```

Or send raw image bytes:
```bash
curl -X POST http://192.168.0.199:8888/image \
  --data-binary @photo.png
```

#### `POST /clear`
Clear screen to white.

```bash
curl -X POST http://192.168.0.199:8888/clear
```

## Architecture

```
it8951-epaper/
├── main.py              # CLI entry point + pattern generators
├── it8951_driver.py     # Core IT8951 driver (SPI, GPIO, display protocol)
├── server/
│   └── server.py        # HTTP API server (text, image, clear endpoints)
├── requirements.txt     # Python dependencies
├── it8951-epaper.service # systemd service file
└── README.md            # This file
```

### Color Convention

This display inverts colors at the hardware level. The driver applies a global
inversion pass in `display_4bpp()` so you can use the intuitive convention:

- **0 = white**, **15 = black** in your code → displays correctly on screen
- PIL images: **0 = black**, **255 = white** (standard PIL convention)

### Refresh Modes

| Mode | Value | Description | Speed |
|------|-------|-------------|-------|
| INIT | 0 | Full clear/flash | ~5s |
| GC16 | 2 | 16-level grayscale, best quality | ~3-5s |
| A2 | 6 | Fast black/white only | ~0.3s |

Use `GC16_MODE` for images and text (best quality).
Use `A2` (via `--mode` parameter) for fast black/white updates.

## How It Works

### SPI Communication

The IT8951 uses a custom SPI protocol with 16-bit commands:

| Operation | Preamble | Data |
|-----------|----------|------|
| Write command | `0x6000` | 16-bit command |
| Write data | `0x0000` | 16-bit data |
| Read data | `0x1000` | dummy `0x0000` → 16-bit data |

All transactions require:
1. Wait for BUSY pin = HIGH (idle)
2. Pull CS (GPIO 229) LOW
3. Send preamble + data via SPI (atomic ioctl call)
4. Pull CS HIGH

The driver uses raw `SPI_IOC_MESSAGE(N)` ioctl calls to send multiple SPI
transfers atomically with CS held low throughout.

### Manual CS Control

The Waveshare HAT's CS is on GPIO 229 (SPI1 CS0). We drive it manually via
`libgpiod` instead of letting the kernel SPI driver handle it. This matches
the Waveshare reference C code approach.

## Troubleshooting

### "Device or resource busy" on GPIO

A previous process didn't release the GPIO lines. Kill it:
```bash
sudo fuser /dev/spidev1.1
sudo kill -9 <PID>
```

### "Busy never released" after reset

- Check that the HAT is properly seated on the GPIO header
- Verify the boot overlay is `spi1-cs1-spidev` (not `cs0-cs1`)
- Check `/dev/spidev1.1` exists: `ls /dev/spidev*`

### All zeros or 0xFFFF in device info

- Wrong CS: make sure you're using `spi1-cs1-spidev` overlay
- GPIO conflict: check `sudo cat /sys/kernel/debug/gpio` — GPIO 229 should NOT be kernel-claimed

### Colors appear inverted

The driver handles this automatically via `display_4bpp()`. If colors are still
wrong, check that you're using `display_4bpp()` or `display_image()` (not
`_write_data_bytes()` directly).

## Credits

- Based on [Waveshare IT8951-ePaper](https://github.com/waveshare/IT8951-ePaper) C code
- Original [waveshare/IT8951](https://github.com/waveshare/IT8951) repository