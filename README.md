# FearTools

Modern GUI toolkit for extracting and converting F.E.A.R. game files (ARCH, BNDL, SND, TEX, dsPack). Supports F.E.A.R. 1, 2, and 3 with batch processing capabilities and a dark-themed interface. Python port of Crypton's and Watto's original tools.

A comprehensive suite of tools for handling various file formats used in the F.E.A.R. game series, featuring both GUI and command-line interfaces.

## Supported Games

- F.E.A.R. (First Encounter Assault Recon)
- F.E.A.R. 2: Project Origin
- F.E.A.R. 3

![FearTools GUI](screenshots/gui.png) *(Screenshot to be added)*

## Features

- **ARCH Extractor**: Extract files from `.arch00` and `.arch01` archives (F.E.A.R. 1)
- **BNDL Extractor**: Extract files from `.bndl` archives (F.E.A.R. 2)
- **SND Converter**: Convert `.snd` files to `.wav` format (All F.E.A.R. games)
- **TEX Converter**: Convert between `.tex` and `.dds` formats (All F.E.A.R. games)
- **dsPack Extractor**: Extract files from `.dsPack` archives with compression support (F.E.A.R. 3)

## Installation

1. Ensure you have Python 3.6+ installed
2. Install the required dependencies:
```bash
pip install PyQt6
```

## Usage

Run the GUI application:
```bash
python UI.py
```

Or use individual tools from the command line:

### ARCH Extractor
```bash
python ArchExtractor.py <arch_file> [output_directory]
```

### BNDL Extractor
```bash
python BndlExtractor.py <bndl_file> [output_directory]
```

### SND Converter
```bash
python SNDExtractor.py <snd_file>
```

### TEX Converter
```bash
# Convert TEX to DDS
python TexConverter.py -tex <input_file> [output_directory]

# Convert DDS to TEX
python TexConverter.py -dds <input_file> [output_directory]

# Batch conversion
python TexConverter.py -batch -tex/-dds <input_directory> [output_directory]
```

### dsPack Extractor
```bash
python dsPACKExtractor.py <dspack_file> [output_directory]
```

## Features in Detail

### ARCH Extractor
- Extract single ARCH files or batch process multiple files
- Maintains original file structure
- Option to delete source files after extraction

### BNDL Extractor
- Extract single BNDL files or batch process multiple files
- Preserves original file structure
- Option to delete source files after extraction

### SND Converter
- Converts SND audio files to standard WAV format
- Supports multi-track SND files
- Creates organized output in 'wavs' directory

### TEX Converter
- Bi-directional conversion between TEX and DDS formats
- Batch processing support
- Preserves texture quality and properties
- Option to delete source files after conversion

### dsPack Extractor (F.E.A.R. 3 Experimental)
- Supports both big-endian and little-endian formats
- Handles compressed and uncompressed files
- Maintains folder structure
- Marks compressed files with [Compressed] tag when compression format is unsupported
- Provides detailed archive analysis

## GUI Features

- Modern dark theme interface
- Progress tracking and status updates
- Batch processing capabilities
- File and folder selection dialogs
- Clear success/failure indicators
- Detailed operation logging

## Technical Details

- Written in Python 3
- Uses PyQt6 for the GUI
- Implements custom decompression algorithms
- Supports various file formats and structures
- Efficient binary file handling
- Robust error handling and validation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Original game files and formats by Monolith Productions
- Original tools and research by Crypton and Watto
- Python port and GUI implementation by the FearTools team

## Support

For issues, questions, or suggestions, please [open an issue](https://github.com/yourusername/FearTools/issues) on GitHub. 