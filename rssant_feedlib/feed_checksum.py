from typing import List, Tuple
from collections import OrderedDict
import itertools
import struct
import hashlib


class FeedChecksum:
    """
    size of 300 items: (4 + 8) * 300 = 3.6KB, can not compress
    +---------+----------------------+------------------------+
    | 1 byte  |           4 * N bytes + 8 * N bytes           |
    +---------+----------------------+------------------------+
    | version |     ident_hash ...   |     content_hash ...   |
    +---------+----------------------+------------------------+
    """

    _key_len = 4
    _val_len = 8
    _key_val_len = _key_len + _val_len

    def __init__(self, items: List[Tuple[bytes, bytes]] = None, version: int = 1):
        if version != 1:
            raise ValueError(f'not support version {version}')
        self.version = version
        self._map = OrderedDict()
        for key, value in items or []:
            self._check_key_value(key, value)
            self._map[key] = value

    def __repr__(self):
        return '<{} version={} size={}>'.format(
            type(self).__name__, self.version, self.size())

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return (self.version == other.version and self._map == other._map)

    def size(self) -> int:
        return len(self._map)

    def copy(self) -> "FeedChecksum":
        items = list(self._map.items())
        return FeedChecksum(items, version=self.version)

    def _hash(self, value: str, length: int) -> bytes:
        return hashlib.md5(value.encode('utf-8')).digest()[:length]

    def update(self, ident: str, content: str) -> bool:
        """
        由于哈希碰撞，可能会出现:
            1. 有更新但内容哈希值没变，导致误判为无更新。不能接受。
            2. 多个ID哈希值一样，导致误判为有更新。可以接受。
        """
        if not ident:
            raise ValueError('ident can not be empty')
        key = self._hash(ident, self._key_len)
        old_sum = self._map.get(key)
        new_sum = self._hash(content, self._val_len)
        if (not old_sum) or old_sum != new_sum:
            self._map[key] = new_sum
            return True
        return False

    def _check_key_value(self, key: bytes, value: bytes):
        if len(key) != self._key_len:
            raise ValueError(f'key length must be {self._key_len} bytes')
        if len(value) != self._val_len:
            raise ValueError(f'value length must be {self._val_len} bytes')

    def dump(self, limit=None) -> bytes:
        length = len(self._map)
        keys_buffer = bytearray()
        vals_buffer = bytearray()
        version_bytes = struct.pack('>B', self.version)
        items = self._map.items()
        if limit is not None and length > limit:
            items = itertools.islice(items, length - limit, length)
        for key, value in items:
            self._check_key_value(key, value)
            keys_buffer.extend(key)
            vals_buffer.extend(value)
        return version_bytes + keys_buffer + vals_buffer

    @classmethod
    def load(cls, data: bytes) -> "FeedChecksum":
        version = struct.unpack('>B', data[:1])[0]
        if version != 1:
            raise ValueError(f'not support version {version}')
        n, remain = divmod(len(data) - 1, cls._key_val_len)
        if remain != 0:
            raise ValueError(f'unexpect data length {len(data)}')
        keys_buffer = memoryview(data)[1: 1 + n * cls._key_len]
        vals_buffer = memoryview(data)[1 + n * cls._key_len:]
        key_packer = struct.Struct(str(cls._key_len) + 's')
        val_packer = struct.Struct(str(cls._val_len) + 's')
        items = []
        keys_iter = key_packer.iter_unpack(keys_buffer)
        vals_iter = val_packer.iter_unpack(vals_buffer)
        for (key,), (value,) in zip(keys_iter, vals_iter):
            items.append((key, value))
        return cls(items, version=version)
