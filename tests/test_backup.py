import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'nested').mkdir()
        (self.source / 'empty').mkdir()
        (self.source / 'nested' / 'hello.txt').write_text('important data\n')
        (self.source / 'binary.bin').write_bytes(bytes(range(256)))

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_including_empty_directory_and_binary(self):
        archive = backup.create(self.source, self.root / 'archives')
        manifest = backup.verify(archive)
        self.assertEqual(len(manifest['files']), 2)
        backup.restore(archive, self.root / 'restored')
        self.assertEqual((self.root / 'restored/binary.bin').read_bytes(), bytes(range(256)))
        self.assertEqual((self.root / 'restored/nested/hello.txt').read_text(), 'important data\n')
        self.assertTrue((self.root / 'restored/empty').is_dir())

    def test_refuses_overwrite_and_recursive_destination(self):
        with self.assertRaises(ValueError):
            backup.create(self.source, self.source / 'backup')
        archive = backup.create(self.source, self.root / 'archives')
        with self.assertRaises(ValueError):
            backup.restore(archive, self.source)

    def test_symlink_not_followed(self):
        (self.source / 'link').symlink_to('/etc/passwd')
        archive = backup.create(self.source, self.root / 'archives')
        self.assertNotIn('link', backup.verify(archive)['files'])

    def test_checksum_corruption_rejected(self):
        good = backup.create(self.source, self.root / 'archives')
        bad = self.root / 'bad.tar.gz'
        with tarfile.open(good) as src, tarfile.open(bad, 'w:gz') as dst:
            for member in src.getmembers():
                stream = src.extractfile(member) if member.isfile() else None
                if member.name == 'data/binary.bin':
                    stream = io.BytesIO(b'x' * member.size)
                dst.addfile(member, stream)
        with self.assertRaisesRegex(ValueError, 'Checksum'):
            backup.restore(bad, self.root / 'restored')
        self.assertFalse((self.root / 'restored').exists())

    def test_path_traversal_rejected(self):
        path = self.root / 'evil.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            info = tarfile.TarInfo('../escape')
            info.size = 1
            archive.addfile(info, io.BytesIO(b'x'))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            backup.restore(path, self.root / 'restored')
        self.assertFalse((self.root / 'escape').exists())

    def test_expansion_limit(self):
        archive = backup.create(self.source, self.root / 'archives')
        with self.assertRaisesRegex(ValueError, 'limit'):
            backup.verify(archive, max_bytes=1)


if __name__ == '__main__':
    unittest.main()
