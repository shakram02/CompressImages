from PIL import Image, ImageFile
from sys import exit, stderr
from os.path import getsize, isfile, isdir, join
from os import remove, rename, walk, stat, path
from stat import S_IWRITE
from shutil import move
from argparse import ArgumentParser
from abc import ABCMeta, abstractmethod


class ProcessBase:
    """Abstract base class for file processors."""
    __metaclass__ = ABCMeta

    def __init__(self):
        self.extensions = []
        self.backup_extension = 'compressimages-backup'

    @abstractmethod
    def process_file(self, filename):
        """Abstract method which carries out the process on the specified file.
        Returns True if successful, False otherwise."""
        pass

    def process_dir(self, path):
        """Recursively processes files in the specified directory matching
        the self.extensions list (case-insensitively)."""

        file_count = 0  # Number of files successfully updated

        for root, dirs, files in walk(path):
            for file in files:
                # Check file extensions against allowed list
                lowercase_file = file.lower()
                matches = False
                for ext in self.extensions:
                    if lowercase_file.endswith('.' + ext):
                        matches = True
                        break
                if matches:
                    # File has eligible extension, so process
                    full_path = join(root, file)
                    if self.process_file(full_path):
                        file_count = file_count + 1
        return file_count


class CompressImage(ProcessBase):
    """Processor which attempts to reduce image file size."""

    def __init__(self, compression_quality):
        ProcessBase.__init__(self)
        self.compression_quality = compression_quality
        self.extensions = ['jpg', 'jpeg', 'png']

    def process_file(self, src_full_path):
        """Renames the specified image to a backup path,
        and writes out the image again with optimal settings."""
        try:
            # Skip read-only files
            if not stat(src_full_path)[0] & S_IWRITE:
                print('Ignoring read-only file "' + src_full_path + '".')
                return False

            # Create a backup
            file_name = path.basename(src_full_path)
            dir_path = path.dirname(src_full_path)
            output_path = path.join(dir_path, self.backup_extension + '-' + file_name)

        except Exception as e:
            stderr.write('Skipping file "' + src_full_path + '" for which backup cannot be made: ' + str(e) + '\n')
            return False

        ok = False

        try:
            # Open the image
            with open(src_full_path, 'rb') as file:
                img = Image.open(file)

                # Check that it's a supported format
                file_format = str(img.format)
                if file_format != 'PNG' and file_format != 'JPEG':
                    print('Ignoring file "' + src_full_path + '" with unsupported format ' + file_format)
                    return False

                # This line avoids problems that can arise saving larger JPEG files with PIL
                ImageFile.MAXBLOCK = img.size[0] * img.size[1]

                # The 'quality' option is ignored for PNG files
                img.save(output_path, quality=self.compression_quality, optimize=True)

            # Check that we've actually made it smaller
            org_size = getsize(src_full_path)
            out_size = getsize(output_path)

            if out_size >= org_size:
                print('Cannot further compress "' + src_full_path + '".')
                return False

            # Successful compression
            ok = True
        except Exception as e:
            stderr.write('Failure whilst processing "' + src_full_path + '": ' + str(e) + '\n')
        return ok


class RestoreBackupImage(ProcessBase):
    """Processor which restores image from backup."""

    def __init__(self):
        ProcessBase.__init__(self)
        self.extensions = [self.backup_extension]

    def process_file(self, filename):
        """Moves the backup file back to its original name."""
        try:
            move(filename, filename[: -(len(self.backup_extension) + 1)])
            return True
        except Exception as e:
            stderr.write('Failed to restore backup file "' + filename + '": ' + str(e) + '\n')
            return False


class DeleteBackupImage(ProcessBase):
    """Processor which deletes backup image."""

    def __init__(self):
        ProcessBase.__init__(self)
        self.extensions = [self.backup_extension]

    def process_file(self, filename):
        """Deletes the specified file."""
        try:
            remove(filename)
            return True
        except Exception as e:
            stderr.write('Failed to delete backup file "' + filename + '": ' + str(e) + '\n')
            return False


if __name__ == "__main__":
    # Argument parsing
    mode_compress = 'compress'
    mode_restore_backup = 'restorebackup'
    mode_delete_backup = 'deletebackup'
    parser = ArgumentParser(description='Reduce file size of PNG and JPEG images.')
    parser.add_argument(
        'path',
        help='File or directory name')
    parser.add_argument(
        '--mode', dest='mode', default=mode_compress,
        choices=[mode_compress, mode_restore_backup, mode_delete_backup],
        help='Mode to run with (default: ' + mode_compress + '). '
             + mode_compress + ': Compress the image(s). '
             + mode_restore_backup + ': Restore the backup images (valid for directory path only). '
             + mode_delete_backup + ': Delete the backup images (valid for directory path only).')

    args = parser.parse_args()

    # Construct processor requested mode
    if args.mode == mode_compress:
        processor = CompressImage(50)
    elif args.mode == mode_restore_backup:
        processor = RestoreBackupImage()
    elif args.mode == mode_delete_backup:
        processor = DeleteBackupImage()
    else:
        raise RuntimeError("No mode selected")

    # Run according to whether path is a file or a directory
    if isfile(args.path):
        if args.mode != mode_compress:
            stderr.write('Mode "' + args.mode + '" supported on directories only.\n')
            exit(1)
        processor.process_file(args.path)
    elif isdir(args.path):
        filecount = processor.process_dir(args.path)
        print('\nSuccessfully updated file count: ' + str(filecount))

    else:
        stderr.write('Invalid path "' + args.path + '"\n')
        exit(1)
