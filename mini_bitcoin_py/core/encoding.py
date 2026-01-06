"""
Deterministic serialization for blockchain data structures.

SERIALIZATION FORMAT:
---------------------
All data is serialized to bytes in a deterministic manner for hashing and signing.
This ensures that the same data always produces the same hash/signature.

Integer encoding: Little-endian, fixed width
- int32: 4 bytes, signed
- uint32: 4 bytes, unsigned
- int64: 8 bytes, signed
- uint64: 8 bytes, unsigned

String/hex encoding:
- Hex strings are converted to bytes
- Length-prefixed with uint32

Variable-length data:
- Arrays prefixed with uint32 count
- Each element serialized consecutively
"""

import struct
from typing import List, Union


def encode_int32(value: int) -> bytes:
    """Encode signed 32-bit integer as little-endian bytes."""
    return struct.pack("<i", value)


def decode_int32(data: bytes) -> int:
    """Decode signed 32-bit integer from little-endian bytes."""
    return struct.unpack("<i", data[:4])[0]


def encode_uint32(value: int) -> bytes:
    """Encode unsigned 32-bit integer as little-endian bytes."""
    return struct.pack("<I", value)


def decode_uint32(data: bytes) -> int:
    """Decode unsigned 32-bit integer from little-endian bytes."""
    return struct.unpack("<I", data[:4])[0]


def encode_int64(value: int) -> bytes:
    """Encode signed 64-bit integer as little-endian bytes."""
    return struct.pack("<q", value)


def decode_int64(data: bytes) -> int:
    """Decode signed 64-bit integer from little-endian bytes."""
    return struct.unpack("<q", data[:8])[0]


def encode_uint64(value: int) -> bytes:
    """Encode unsigned 64-bit integer as little-endian bytes."""
    return struct.pack("<Q", value)


def decode_uint64(data: bytes) -> int:
    """Decode unsigned 64-bit integer from little-endian bytes."""
    return struct.unpack("<Q", data[:8])[0]


def encode_varint(value: int) -> bytes:
    """
    Encode variable-length integer (Bitcoin-style varint).

    - 0-252: 1 byte
    - 253-65535: 0xfd + 2 bytes (little-endian)
    - 65536-4294967295: 0xfe + 4 bytes (little-endian)
    - Larger: 0xff + 8 bytes (little-endian)
    """
    if value < 0:
        raise ValueError("Varint cannot be negative")
    if value < 0xFD:
        return bytes([value])
    elif value <= 0xFFFF:
        return bytes([0xFD]) + struct.pack("<H", value)
    elif value <= 0xFFFFFFFF:
        return bytes([0xFE]) + struct.pack("<I", value)
    else:
        return bytes([0xFF]) + struct.pack("<Q", value)


def decode_varint(data: bytes) -> tuple[int, int]:
    """
    Decode variable-length integer.

    Returns:
        Tuple of (value, bytes_consumed)
    """
    if len(data) == 0:
        raise ValueError("Empty data for varint")

    first = data[0]
    if first < 0xFD:
        return first, 1
    elif first == 0xFD:
        return struct.unpack("<H", data[1:3])[0], 3
    elif first == 0xFE:
        return struct.unpack("<I", data[1:5])[0], 5
    else:
        return struct.unpack("<Q", data[1:9])[0], 9


def encode_hex_bytes(hex_string: str) -> bytes:
    """
    Encode a hex string as length-prefixed bytes.

    Format: varint(length) + raw_bytes
    """
    raw = bytes.fromhex(hex_string)
    return encode_varint(len(raw)) + raw


def decode_hex_bytes(data: bytes) -> tuple[str, int]:
    """
    Decode length-prefixed bytes to hex string.

    Returns:
        Tuple of (hex_string, bytes_consumed)
    """
    length, varint_size = decode_varint(data)
    raw = data[varint_size : varint_size + length]
    return raw.hex(), varint_size + length


def encode_fixed_bytes(hex_string: str, expected_length: int) -> bytes:
    """
    Encode a hex string as fixed-length bytes (no length prefix).

    Args:
        hex_string: Hex string to encode
        expected_length: Expected byte length (hex_string should be 2x this)
    """
    raw = bytes.fromhex(hex_string)
    if len(raw) != expected_length:
        raise ValueError(f"Expected {expected_length} bytes, got {len(raw)}")
    return raw


def decode_fixed_bytes(data: bytes, length: int) -> tuple[str, int]:
    """
    Decode fixed-length bytes to hex string.

    Returns:
        Tuple of (hex_string, bytes_consumed)
    """
    return data[:length].hex(), length


def encode_string(s: str) -> bytes:
    """Encode a UTF-8 string as length-prefixed bytes."""
    encoded = s.encode("utf-8")
    return encode_varint(len(encoded)) + encoded


def decode_string(data: bytes) -> tuple[str, int]:
    """
    Decode length-prefixed UTF-8 string.

    Returns:
        Tuple of (string, bytes_consumed)
    """
    length, varint_size = decode_varint(data)
    raw = data[varint_size : varint_size + length]
    return raw.decode("utf-8"), varint_size + length


def encode_list(items: List[bytes]) -> bytes:
    """
    Encode a list of already-serialized items.

    Format: varint(count) + item1 + item2 + ...
    """
    result = encode_varint(len(items))
    for item in items:
        result += item
    return result


def encode_target(target: int) -> bytes:
    """
    Encode a 256-bit target as 32 bytes (big-endian for PoW comparison).

    The target is stored as a 32-byte big-endian integer for easy
    comparison with block hashes.
    """
    return target.to_bytes(32, byteorder="big")


def decode_target(data: bytes) -> tuple[int, int]:
    """
    Decode 32-byte big-endian target.

    Returns:
        Tuple of (target_int, bytes_consumed=32)
    """
    return int.from_bytes(data[:32], byteorder="big"), 32
