import os
import struct
from pathlib import Path
from typing import Optional, Tuple

# Constants for WAV format - pre-compile markers and structs
RIFF_MARKER = struct.unpack('<I', b'RIFF')[0]
WAVE_MARKER = struct.unpack('<I', b'WAVE')[0]
FMT_MARKER = struct.unpack('<I', b'fmt ')[0]
DATA_MARKER = struct.unpack('<I', b'data')[0]

# Pre-compile struct formats for better performance
HEADER_STRUCT = struct.Struct('<6I')  # First 24 bytes (6 DWORDs)
UNK_TABLE_STRUCT = struct.Struct('<65I')  # UnkTable with 65 elements
CHUNK_HEADER_STRUCT = struct.Struct('<6I2H2I2H')  # 40 bytes total
RIFF_HEADER_STRUCT = struct.Struct('<4I')  # RIFF header (4 DWORDs)
FMT_CHUNK_STRUCT = struct.Struct('<2H2I2H')  # fmt chunk (16 bytes)
DATA_HEADER_STRUCT = struct.Struct('<2I')  # data chunk header (2 DWORDs)


class SNDHeader:
    __slots__ = ('Version', 'FileCount', 'ChunkEntryOffset', 'ChunkInfoOffset',
                 'ChunkBaseOffset', 'UnkCount', 'UnkTable')
    
    def __init__(self, data: bytes):
        if len(data) != 284:  # 24 bytes header + 260 bytes UnkTable
            raise ValueError(f"Invalid SNDHeader size. Got {len(data)} bytes, expected 284 bytes")

        # First 24 bytes (6 DWORDs)
        header_values = HEADER_STRUCT.unpack(data[:24])
        (self.Version,  # Always 2
         self.FileCount,
         self.ChunkEntryOffset,  # First TSNDChunkEntry, Size of Table = FileCount * 8
         self.ChunkInfoOffset,  # First TSNDChunkInfo
         self.ChunkBaseOffset,  # First TSNDChunkHeader
         self.UnkCount) = header_values

        # UnkTable with 65 elements (Array[0..64])
        self.UnkTable = list(UNK_TABLE_STRUCT.unpack(data[24:284]))


class SNDChunkHeader:
    __slots__ = ('TotalSize', 'SoundType', 'SNDChunkSize', 'WAVEHeaderSize',
                 'DataOffset', 'DataSize', 'ComCode', 'ChannelCount',
                 'SampleRate', 'StreamRate', 'BlockAlign', 'SampleSize')
    
    def __init__(self, data: bytes):
        if len(data) != 40:  # 40 bytes
            raise ValueError(f"Invalid SNDChunkHeader size. Got {len(data)} bytes, expected 40 bytes")

        # Unpack exactly as per the original structure (40 bytes total)
        values = CHUNK_HEADER_STRUCT.unpack(data)
        (self.TotalSize,  # DWORD
         self.SoundType,  # DWORD
         self.SNDChunkSize,  # DWORD (always 16)
         self.WAVEHeaderSize,  # DWORD (always 40)
         self.DataOffset,  # DWORD (always 56)
         self.DataSize,  # DWORD
         self.ComCode,  # WORD
         self.ChannelCount,  # WORD
         self.SampleRate,  # DWORD
         self.StreamRate,  # DWORD
         self.BlockAlign,  # WORD
         self.SampleSize  # WORD
         ) = values


def write_wav_header(outfile, chunk_header: SNDChunkHeader, in_size: int) -> None:
    """Write WAV header to the output file."""
    # RIFF header
    RIFF_HEADER_STRUCT.pack_into(outfile, 0,
        RIFF_MARKER,
        in_size + 36,  # Total size
        WAVE_MARKER,
        FMT_MARKER
    )

    # fmt chunk
    outfile.write(struct.pack('<I', 16))  # fmt chunk size
    FMT_CHUNK_STRUCT.pack_into(outfile, outfile.tell(),
        chunk_header.ComCode,
        chunk_header.ChannelCount,
        chunk_header.SampleRate,
        chunk_header.StreamRate,
        chunk_header.BlockAlign,
        chunk_header.SampleSize
    )

    # data chunk
    DATA_HEADER_STRUCT.pack_into(outfile, outfile.tell(),
        DATA_MARKER,
        in_size
    )


def convert_sound_to_wave(file_name: Path) -> bool:
    """Convert SND file to WAV format."""
    try:
        # Create wavs directory if it doesn't exist
        wavs_dir = Path('wavs')
        wavs_dir.mkdir(exist_ok=True)

        # Create subdirectory named after the original file
        output_dir = wavs_dir / file_name.stem
        output_dir.mkdir(exist_ok=True)

        print(f"Output directory: {output_dir}")

        with open(file_name, 'rb') as infile:
            # Read SND header
            header_data = infile.read(284)
            if len(header_data) != 284:
                print(f"Error: Invalid header size. Got {len(header_data)} bytes")
                return False

            snd_header = SNDHeader(header_data)
            print(f"SND Info:")
            print(f"  Version: {snd_header.Version}")
            print(f"  Number of files: {snd_header.FileCount}")
            print(f"  Chunk base offset: {snd_header.ChunkBaseOffset}")

            # Move to the chunk base offset where audio data starts
            infile.seek(snd_header.ChunkBaseOffset)

            # Process each sound file
            for file_index in range(snd_header.FileCount):
                if not _process_sound_file(infile, file_index, file_name, output_dir):
                    return False

        return True

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def _process_sound_file(infile, file_index: int, source_file: Path, output_dir: Path) -> bool:
    """Process a single sound file from the SND archive."""
    try:
        # Read chunk header
        chunk_data = infile.read(40)
        if len(chunk_data) != 40:
            print(f"Error: Invalid chunk header size for file {file_index}")
            return False

        chunk_header = SNDChunkHeader(chunk_data)
        print(f"\nProcessing file {file_index}:")
        print(f"  Sample Rate: {chunk_header.SampleRate}")
        print(f"  Channels: {chunk_header.ChannelCount}")
        print(f"  Bits Per Sample: {chunk_header.SampleSize}")

        # Calculate input size
        in_size = chunk_header.DataSize + 24

        # Read sound data
        sound_data = infile.read(in_size)
        if len(sound_data) != in_size:
            print(f"Error: Incomplete sound data for file {file_index}")
            print(f"Expected {in_size} bytes, got {len(sound_data)} bytes")
            return False

        # Create output WAV file in the subdirectory
        out_path = output_dir / f"{source_file.stem}_{file_index}.wav"
        with open(out_path, 'wb') as outfile:
            # Write WAV header structure
            write_wav_header(outfile, chunk_header, in_size)
            
            # Write sound data
            outfile.write(sound_data)

        print(f"Created: {out_path}")
        return True

    except Exception as e:
        print(f"Error processing file {file_index}: {str(e)}")
        return False


def main():
    print('--------------------------------')
    print('SND Extractor v0.1')
    print('Python port by ChatGPT')
    print('--------------------------------')

    import sys
    if len(sys.argv) < 2:
        print("Usage: python script.py <snd_file>")
        sys.exit(1)

    source_file = Path(sys.argv[1])
    if not source_file.exists():
        print("Input file not found!")
        sys.exit(1)

    print(f'Extracting: {source_file}')
    success = convert_sound_to_wave(source_file)
    print('Extracting finished...' if success else 'Extracting failed!')
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()