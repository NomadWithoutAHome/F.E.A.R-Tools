import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QTabWidget,
                             QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                             QFileDialog, QProgressBar, QTextEdit, QGroupBox,
                             QCheckBox, QComboBox,)
from PyQt6.QtCore import  QThread, pyqtSignal
import io
from contextlib import redirect_stdout

# Import your existing tools
from ArchExtractor import archive_extract, archive_batch_extract
from BndlExtractor import extract_bundle_file, batch_extract_bndl
from SNDExtractor import convert_sound_to_wave
from TexConverter import (tex_convert_to_dds, dds_convert_to_tex,
                          batch_convert_tex_to_dds, batch_convert_dds_to_tex)
from dsPACKExtractor import DSPackFile, MiniPackDecompressor


class WorkerThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            # Capture all stdout to our progress signal
            output = io.StringIO()
            with redirect_stdout(output):
                result = self.function(*self.args, **self.kwargs)
                
            # Send captured output to log
            output_str = output.getvalue()
            if output_str:
                for line in output_str.splitlines():
                    self.progress.emit(line)
                    
            self.finished.emit(result)
        except Exception as e:
            self.progress.emit(f"Error: {str(e)}")
            self.finished.emit(False)

class DSPackWrapper(DSPackFile):
    def __init__(self, filename, progress_callback=None):
        super().__init__(filename)
        self.progress_callback = progress_callback

    def print_message(self, message):
        """Override print to use the progress callback"""
        if self.progress_callback:
            self.progress_callback(message)
        else:
            print(message)

    def analyze(self):
        """Override analyze to use custom print"""
        # Read all directory structures
        self.read_header()
        self.read_names_directory()
        self.read_file_entries()
        self.read_folder_entries()
        
        # Build folder paths
        folder_paths = self.build_folder_paths()
        
        # Print analysis
        self.print_message(f"\n[Archive Analysis: {os.path.basename(self.filename)}]")
        self.print_message(f"{'=' * 50}")
        self.print_message(f"Format: {'Big-endian' if self.big_endian else 'Little-endian'}")
        self.print_message(f"Files: {len(self.files)}")
        self.print_message(f"Folders: {len(self.folders)}")
        
        self.print_message("\n[Folder Structure]")
        for i, path in folder_paths.items():
            folder = self.folders[i]
            file_count = folder['last_file'] - folder['first_file'] + 1 if folder['first_file'] >= 0 else 0
            self.print_message(f"  {path}/ ({file_count} files)")
        
        self.print_message("\n[Sample Files]")
        for file in self.files[:5]:  # Show first 5 files
            comp_ratio = (1 - file['compressed_size'] / file['decompressed_size']) * 100 if file['decompressed_size'] > 0 else 0
            self.print_message(f"  * {file['name']}")
            self.print_message(f"    Size: {file['decompressed_size']:,} bytes")
            if comp_ratio > 0:
                self.print_message(f"    Compression: {comp_ratio:.1f}%")
            self.print_message("")

    def extract_file(self, file_entry):
        """Override extract_file to use custom print"""
        if file_entry['compressed_size'] == 0:
            return None, False
        
        # Read the compressed data
        self.file.seek(file_entry['data_offset'])
        compressed_data = self.file.read(file_entry['compressed_size'])
        
        # If the file is not compressed, return it as-is
        if file_entry['compressed_size'] == file_entry['decompressed_size']:
            self.print_message("  > File is not compressed")
            return compressed_data, False
        
        # Basic validation check: ensure compressed data is smaller than decompressed size
        if len(compressed_data) >= file_entry['decompressed_size']:
            self.print_message("(!!) Invalid compression: compressed size larger than decompressed size")
            return compressed_data, True
        
        # Try to decompress the data
        try:
            decompressor = MiniPackDecompressor()
            data = decompressor.decompress(compressed_data, file_entry['decompressed_size'])
            self.print_message(f"  > Successfully decompressed ({file_entry['compressed_size']:,} -> {len(data):,} bytes)")
            return data, False
        except IndexError:
            # For bytearray index out of range errors, extract the file as-is
            self.print_message("(!!) Unknown compression format: extracting as-is")
            return compressed_data, True
        except (KeyboardInterrupt, Exception) as e:
            self.print_message(f"(!!) Decompression error: {str(e)}")
            return compressed_data, True

class FearToolsGUI(QMainWindow):
    def create_arch_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Single file group
        single_group = QGroupBox("Single File Extraction")
        single_layout = QVBoxLayout(single_group)

        file_layout = QHBoxLayout()
        self.arch_file_label = QLabel("No file selected")
        select_file_btn = QPushButton("Select ARCH File")
        select_file_btn.clicked.connect(lambda: self.select_file("arch00, arch01", self.arch_file_label))
        file_layout.addWidget(select_file_btn)
        file_layout.addWidget(self.arch_file_label)
        file_layout.addStretch()

        output_layout = QHBoxLayout()
        self.arch_output_label = QLabel("Output folder: Same as input")
        select_output_btn = QPushButton("Select Output")
        select_output_btn.clicked.connect(lambda: self.select_output_folder(self.arch_output_label))
        output_layout.addWidget(select_output_btn)
        output_layout.addWidget(self.arch_output_label)
        output_layout.addStretch()

        self.arch_delete_check = QCheckBox("Delete source files after extraction")

        extract_btn = QPushButton("Extract File")
        extract_btn.clicked.connect(lambda: self.extract_arch_file(single=True))

        single_layout.addLayout(file_layout)
        single_layout.addLayout(output_layout)
        single_layout.addWidget(self.arch_delete_check)
        single_layout.addWidget(extract_btn)

        # Batch processing group
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QVBoxLayout(batch_group)

        folder_layout = QHBoxLayout()
        self.arch_folder_label = QLabel("No folder selected")
        select_folder_btn = QPushButton("Select Folder")
        select_folder_btn.clicked.connect(lambda: self.select_folder(self.arch_folder_label))
        folder_layout.addWidget(select_folder_btn)
        folder_layout.addWidget(self.arch_folder_label)
        folder_layout.addStretch()

        batch_output_layout = QHBoxLayout()
        self.arch_batch_output_label = QLabel("Output folder: Same as input")
        select_batch_output_btn = QPushButton("Select Output")
        select_batch_output_btn.clicked.connect(
            lambda: self.select_output_folder(self.arch_batch_output_label))
        batch_output_layout.addWidget(select_batch_output_btn)
        batch_output_layout.addWidget(self.arch_batch_output_label)
        batch_output_layout.addStretch()

        batch_extract_btn = QPushButton("Batch Extract")
        batch_extract_btn.clicked.connect(lambda: self.extract_arch_file(single=False))

        batch_layout.addLayout(folder_layout)
        batch_layout.addLayout(batch_output_layout)
        batch_layout.addWidget(batch_extract_btn)

        layout.addWidget(single_group)
        layout.addWidget(batch_group)
        layout.addStretch()

        return widget

    def create_bndl_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Single file group
        single_group = QGroupBox("Single File Extraction")
        single_layout = QVBoxLayout(single_group)

        file_layout = QHBoxLayout()
        self.bndl_file_label = QLabel("No file selected")
        select_file_btn = QPushButton("Select BNDL File")
        select_file_btn.clicked.connect(lambda: self.select_file("bndl", self.bndl_file_label))
        file_layout.addWidget(select_file_btn)
        file_layout.addWidget(self.bndl_file_label)
        file_layout.addStretch()

        output_layout = QHBoxLayout()
        self.bndl_output_label = QLabel("Output folder: Same as input")
        select_output_btn = QPushButton("Select Output")
        select_output_btn.clicked.connect(lambda: self.select_output_folder(self.bndl_output_label))
        output_layout.addWidget(select_output_btn)
        output_layout.addWidget(self.bndl_output_label)
        output_layout.addStretch()

        self.bndl_delete_check = QCheckBox("Delete source files after extraction")

        extract_btn = QPushButton("Extract File")
        extract_btn.clicked.connect(lambda: self.extract_bndl_file(single=True))

        single_layout.addLayout(file_layout)
        single_layout.addLayout(output_layout)
        single_layout.addWidget(self.bndl_delete_check)
        single_layout.addWidget(extract_btn)

        # Batch processing group
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QVBoxLayout(batch_group)

        folder_layout = QHBoxLayout()
        self.bndl_folder_label = QLabel("No folder selected")
        select_folder_btn = QPushButton("Select Folder")
        select_folder_btn.clicked.connect(lambda: self.select_folder(self.bndl_folder_label))
        folder_layout.addWidget(select_folder_btn)
        folder_layout.addWidget(self.bndl_folder_label)
        folder_layout.addStretch()

        batch_output_layout = QHBoxLayout()
        self.bndl_batch_output_label = QLabel("Output folder: Same as input")
        select_batch_output_btn = QPushButton("Select Output")
        select_batch_output_btn.clicked.connect(
            lambda: self.select_output_folder(self.bndl_batch_output_label))
        batch_output_layout.addWidget(select_batch_output_btn)
        batch_output_layout.addWidget(self.bndl_batch_output_label)
        batch_output_layout.addStretch()

        batch_extract_btn = QPushButton("Batch Extract")
        batch_extract_btn.clicked.connect(lambda: self.extract_bndl_file(single=False))

        batch_layout.addLayout(folder_layout)
        batch_layout.addLayout(batch_output_layout)
        batch_layout.addWidget(batch_extract_btn)

        layout.addWidget(single_group)
        layout.addWidget(batch_group)
        layout.addStretch()

        return widget

    def create_snd_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Single file group
        single_group = QGroupBox("Sound File Conversion")
        single_layout = QVBoxLayout(single_group)

        file_layout = QHBoxLayout()
        self.snd_file_label = QLabel("No file selected")
        select_file_btn = QPushButton("Select SND File")
        select_file_btn.clicked.connect(lambda: self.select_file("snd", self.snd_file_label))
        file_layout.addWidget(select_file_btn)
        file_layout.addWidget(self.snd_file_label)
        file_layout.addStretch()

        output_layout = QHBoxLayout()
        self.snd_output_label = QLabel("Output folder: ./wavs/")
        select_output_btn = QPushButton("Select Output")
        select_output_btn.clicked.connect(lambda: self.select_output_folder(self.snd_output_label))
        output_layout.addWidget(select_output_btn)
        output_layout.addWidget(self.snd_output_label)
        output_layout.addStretch()

        self.snd_delete_check = QCheckBox("Delete source files after conversion")

        convert_btn = QPushButton("Convert to WAV")
        convert_btn.clicked.connect(self.convert_snd_file)

        single_layout.addLayout(file_layout)
        single_layout.addLayout(output_layout)
        single_layout.addWidget(self.snd_delete_check)
        single_layout.addWidget(convert_btn)

        layout.addWidget(single_group)
        layout.addStretch()

        return widget

    def create_tex_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Single file group
        single_group = QGroupBox("Single File Conversion")
        single_layout = QVBoxLayout(single_group)

        file_layout = QHBoxLayout()
        self.tex_file_label = QLabel("No file selected")
        select_file_btn = QPushButton("Select File")
        select_file_btn.clicked.connect(lambda: self.select_file("tex,dds", self.tex_file_label))
        file_layout.addWidget(select_file_btn)
        file_layout.addWidget(self.tex_file_label)
        file_layout.addStretch()

        output_layout = QHBoxLayout()
        self.tex_output_label = QLabel("Output folder: Same as input")
        select_output_btn = QPushButton("Select Output")
        select_output_btn.clicked.connect(lambda: self.select_output_folder(self.tex_output_label))
        output_layout.addWidget(select_output_btn)
        output_layout.addWidget(self.tex_output_label)
        output_layout.addStretch()

        self.tex_delete_check = QCheckBox("Delete source files after conversion")

        convert_btn = QPushButton("Convert File")
        convert_btn.clicked.connect(lambda: self.convert_tex_file(single=True))

        single_layout.addLayout(file_layout)
        single_layout.addLayout(output_layout)
        single_layout.addWidget(self.tex_delete_check)
        single_layout.addWidget(convert_btn)

        # Batch processing group
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QVBoxLayout(batch_group)

        folder_layout = QHBoxLayout()
        self.tex_folder_label = QLabel("No folder selected")
        select_folder_btn = QPushButton("Select Folder")
        select_folder_btn.clicked.connect(lambda: self.select_folder(self.tex_folder_label))
        folder_layout.addWidget(select_folder_btn)
        folder_layout.addWidget(self.tex_folder_label)
        folder_layout.addStretch()

        batch_output_layout = QHBoxLayout()
        self.tex_batch_output_label = QLabel("Output folder: Same as input")
        select_batch_output_btn = QPushButton("Select Output")
        select_batch_output_btn.clicked.connect(
            lambda: self.select_output_folder(self.tex_batch_output_label))
        batch_output_layout.addWidget(select_batch_output_btn)
        batch_output_layout.addWidget(self.tex_batch_output_label)
        batch_output_layout.addStretch()

        conversion_type = QHBoxLayout()
        self.tex_conversion_combo = QComboBox()
        self.tex_conversion_combo.addItems(["TEX to DDS", "DDS to TEX"])
        conversion_type.addWidget(QLabel("Conversion Type:"))
        conversion_type.addWidget(self.tex_conversion_combo)
        conversion_type.addStretch()

        batch_convert_btn = QPushButton("Batch Convert")
        batch_convert_btn.clicked.connect(lambda: self.convert_tex_file(single=False))

        batch_layout.addLayout(folder_layout)
        batch_layout.addLayout(batch_output_layout)
        batch_layout.addLayout(conversion_type)
        batch_layout.addWidget(batch_convert_btn)

        layout.addWidget(single_group)
        layout.addWidget(batch_group)
        layout.addStretch()

        return widget

    def create_dspack_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Single file group
        single_group = QGroupBox("Single File Extraction")
        single_layout = QVBoxLayout(single_group)

        file_layout = QHBoxLayout()
        self.dspack_file_label = QLabel("No file selected")
        select_file_btn = QPushButton("Select dsPack File")
        select_file_btn.clicked.connect(lambda: self.select_file("dspack", self.dspack_file_label))
        file_layout.addWidget(select_file_btn)
        file_layout.addWidget(self.dspack_file_label)
        file_layout.addStretch()

        output_layout = QHBoxLayout()
        self.dspack_output_label = QLabel("Output folder: Same as input")
        select_output_btn = QPushButton("Select Output")
        select_output_btn.clicked.connect(lambda: self.select_output_folder(self.dspack_output_label))
        output_layout.addWidget(select_output_btn)
        output_layout.addWidget(self.dspack_output_label)
        output_layout.addStretch()

        extract_btn = QPushButton("Extract File")
        extract_btn.clicked.connect(lambda: self.extract_dspack_file(single=True))

        single_layout.addLayout(file_layout)
        single_layout.addLayout(output_layout)
        single_layout.addWidget(extract_btn)

        # Batch processing group
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QVBoxLayout(batch_group)

        folder_layout = QHBoxLayout()
        self.dspack_folder_label = QLabel("No folder selected")
        select_folder_btn = QPushButton("Select Folder")
        select_folder_btn.clicked.connect(lambda: self.select_folder(self.dspack_folder_label))
        folder_layout.addWidget(select_folder_btn)
        folder_layout.addWidget(self.dspack_folder_label)
        folder_layout.addStretch()

        batch_output_layout = QHBoxLayout()
        self.dspack_batch_output_label = QLabel("Output folder: Same as input")
        select_batch_output_btn = QPushButton("Select Output")
        select_batch_output_btn.clicked.connect(
            lambda: self.select_output_folder(self.dspack_batch_output_label))
        batch_output_layout.addWidget(select_batch_output_btn)
        batch_output_layout.addWidget(self.dspack_batch_output_label)
        batch_output_layout.addStretch()

        batch_extract_btn = QPushButton("Batch Extract")
        batch_extract_btn.clicked.connect(lambda: self.extract_dspack_file(single=False))

        batch_layout.addLayout(folder_layout)
        batch_layout.addLayout(batch_output_layout)
        batch_layout.addWidget(batch_extract_btn)

        layout.addWidget(single_group)
        layout.addWidget(batch_group)
        layout.addStretch()

        return widget

    def extract_arch_file(self, single=True):
        """Handle ARCH file extraction"""
        try:
            if single and hasattr(self, 'current_file'):
                output_dir = getattr(self, 'output_folder', self.current_file.parent)
                self.worker = WorkerThread(
                    archive_extract,
                    self.current_file,
                    output_dir
                )
            elif not single and hasattr(self, 'current_folder'):
                output_dir = getattr(self, 'output_folder', self.current_folder)
                self.worker = WorkerThread(
                    archive_batch_extract,
                    self.current_folder,
                    output_dir,
                    self.arch_delete_check.isChecked()
                )
            else:
                self.log_message("Please select a file or folder first")
                return

            self.worker.progress.connect(self.log_message)
            self.worker.finished.connect(self.operation_finished)
            self.worker.start()
            self.progress_bar.setRange(0, 0)  # Show indeterminate progress
        except Exception as e:
            self.log_message(f"Error: {str(e)}")

    def extract_bndl_file(self, single=True):
        """Handle BNDL file extraction"""
        try:
            if single and hasattr(self, 'current_file'):
                output_dir = getattr(self, 'output_folder', self.current_file.parent)
                self.worker = WorkerThread(
                    extract_bundle_file,
                    self.current_file,
                    output_dir
                )
            elif not single and hasattr(self, 'current_folder'):
                output_dir = getattr(self, 'output_folder', self.current_folder)
                self.worker = WorkerThread(
                    batch_extract_bndl,
                    self.current_folder,
                    output_dir,
                    self.bndl_delete_check.isChecked()
                )
            else:
                self.log_message("Please select a file or folder first")
                return

            self.worker.progress.connect(self.log_message)
            self.worker.finished.connect(self.operation_finished)
            self.worker.start()
            self.progress_bar.setRange(0, 0)
        except Exception as e:
            self.log_message(f"Error: {str(e)}")

    def convert_snd_file(self):
        """Handle SND file conversion"""
        try:
            if hasattr(self, 'current_file'):
                self.worker = WorkerThread(
                    convert_sound_to_wave,
                    self.current_file
                )
                self.worker.progress.connect(self.log_message)
                self.worker.finished.connect(self.operation_finished)
                self.worker.start()
                self.progress_bar.setRange(0, 0)
            else:
                self.log_message("Please select a file first")
        except Exception as e:
            self.log_message(f"Error: {str(e)}")

    def convert_tex_file(self, single=True):
        """Handle TEX file conversion"""
        try:
            if single and hasattr(self, 'current_file'):
                output_dir = getattr(self, 'output_folder', self.current_file.parent)
                is_tex = self.current_file.suffix.lower() == '.tex'

                if is_tex:
                    target_file = output_dir / self.current_file.with_suffix('.dds').name
                    self.worker = WorkerThread(tex_convert_to_dds, self.current_file, target_file)
                else:
                    target_file = output_dir / self.current_file.with_suffix('.tex').name
                    self.worker = WorkerThread(dds_convert_to_tex, self.current_file, target_file)

            elif not single and hasattr(self, 'current_folder'):
                output_dir = getattr(self, 'output_folder', self.current_folder)
                is_tex_to_dds = self.tex_conversion_combo.currentText() == "TEX to DDS"

                if is_tex_to_dds:
                    self.worker = WorkerThread(
                        batch_convert_tex_to_dds,
                        self.current_folder,
                        output_dir,
                        self.tex_delete_check.isChecked()
                    )
                else:
                    self.worker = WorkerThread(
                        batch_convert_dds_to_tex,
                        self.current_folder,
                        output_dir,
                        self.tex_delete_check.isChecked()
                    )
            else:
                self.log_message("Please select a file or folder first")
                return

            self.worker.progress.connect(self.log_message)
            self.worker.finished.connect(self.operation_finished)
            self.worker.start()
            self.progress_bar.setRange(0, 0)
        except Exception as e:
            self.log_message(f"Error: {str(e)}")

    def extract_dspack_file(self, single=True):
        """Handle dsPack file extraction"""
        try:
            if single and hasattr(self, 'current_file'):
                output_dir = getattr(self, 'output_folder', self.current_file.parent / self.current_file.stem)
                self.worker = WorkerThread(
                    self._extract_single_dspack,
                    self.current_file,
                    output_dir
                )
            elif not single and hasattr(self, 'current_folder'):
                output_dir = getattr(self, 'output_folder', self.current_folder)
                self.worker = WorkerThread(
                    self._extract_batch_dspack,
                    self.current_folder,
                    output_dir
                )
            else:
                self.log_message("Please select a file or folder first")
                return

            self.worker.progress.connect(self.log_message)
            self.worker.finished.connect(self.operation_finished)
            self.worker.start()
            self.progress_bar.setRange(0, 0)  # Show indeterminate progress
        except Exception as e:
            self.log_message(f"Error: {str(e)}")

    def _extract_single_dspack(self, file_path, output_dir):
        """Extract a single dsPack file"""
        try:
            with DSPackWrapper(file_path, self.worker.progress.emit) as dspack:
                dspack.analyze()
                dspack.extract_all_files(output_dir)
            return True
        except Exception as e:
            self.log_message(f"Error extracting {file_path}: {str(e)}")
            return False

    def _extract_batch_dspack(self, folder_path, output_dir):
        """Extract all dsPack files in a folder"""
        try:
            success = True
            for file in folder_path.glob("*.dspack"):
                try:
                    output_subdir = output_dir / file.stem
                    with DSPackWrapper(file, self.worker.progress.emit) as dspack:
                        dspack.analyze()
                        dspack.extract_all_files(output_subdir)
                except Exception as e:
                    self.log_message(f"Error extracting {file}: {str(e)}")
                    success = False
            return success
        except Exception as e:
            self.log_message(f"Error processing folder {folder_path}: {str(e)}")
            return False

    def __init__(self):
        super().__init__()
        self.setWindowTitle("F.E.A.R. Tools")
        self.setMinimumSize(800, 600)

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Add tabs for each tool
        tabs.addTab(self.create_arch_tab(), "ARCH Extractor")
        tabs.addTab(self.create_bndl_tab(), "BNDL Extractor")
        tabs.addTab(self.create_snd_tab(), "SND Converter")
        tabs.addTab(self.create_tex_tab(), "TEX Converter")
        tabs.addTab(self.create_dspack_tab(), "dsPack Extractor")

        # Status area at the bottom
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(100)
        layout.addWidget(self.log_output)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.apply_styles()

    def apply_styles(self):
        """Apply the dark theme styling to all widgets"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTabWidget {
                background-color: #333333;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
            }
            QTabBar::tab {
                background-color: #444444;
                color: #ffffff;
                padding: 8px 20px;
                margin: 2px;
            }
            QTabBar::tab:selected {
                background-color: #666666;
            }
            QPushButton {
                background-color: #0d47a1;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:disabled {
                background-color: #666666;
            }
            QLabel {
                color: #ffffff;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QGroupBox {
                color: #ffffff;
                border: 1px solid #555555;
                margin-top: 1ex;
                padding-top: 1ex;
            }
            QGroupBox::title {
                color: #ffffff;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QCheckBox {
                color: #ffffff;
            }
            QComboBox {
                background-color: #444444;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
                min-width: 100px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #1e1e1e;
                color: #ffffff;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0d47a1;
            }
        """)

    def log_message(self, message):
        """Add message to log output"""
        self.log_output.append(message)
        # Ensure the latest message is visible
        self.log_output.verticalScrollBar().setValue(
            self.log_output.verticalScrollBar().maximum()
        )

    def select_file(self, extensions, label):
        """File selection dialog"""
        extensions = extensions.split(',')
        filter_str = f"FEAR Files ({' '.join(f'*.{ext}' for ext in extensions)})"
        file_name, _ = QFileDialog.getOpenFileName(
            self, f"Select file", "", filter_str)
        if file_name:
            self.current_file = Path(file_name)
            label.setText(str(self.current_file))

    def select_folder(self, label):
        """Folder selection dialog"""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.current_folder = Path(folder)
            label.setText(str(self.current_folder))

    def select_output_folder(self, label):
        """Output folder selection dialog"""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder = Path(folder)
            label.setText(f"Output folder: {self.output_folder}")

    def operation_finished(self, success):
        """Handle completion of operations"""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)
        self.log_message("Operation completed successfully" if success else "Operation failed")

def main():
    app = QApplication(sys.argv)

        # Set application-wide style defaults
    app.setStyle('Fusion')  # Modern style base

        # Create and show the main window
    window = FearToolsGUI()
    window.show()

        # Start the event loop
    sys.exit(app.exec())

if __name__ == '__main__':
    main()