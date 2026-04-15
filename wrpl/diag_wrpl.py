import zlib, struct
from pathlib import Path

path = 'wrpl/replays/650013b0028f640/0000.wrpl'
data = Path(path).read_bytes()
print(f'Magic: {data[:4].hex()}')
print(f'Taille: {len(data)}')

HEADER_FORMAT = '<4si128s260s128s128s32siB35sI4sQB3sIH30s128sIII48s128s128s2s'
u = struct.unpack_from(HEADER_FORMAT, data, 0)
settings_size = u[16]
results_at    = u[7]
pkt_off = 1226 + settings_size

print(f'settings_blk_size: {settings_size}')
print(f'pkt_offset: {pkt_off}')
print(f'results_at: {results_at}')

raw = data[pkt_off:results_at] if results_at > pkt_off else data[pkt_off:]
print(f'Stream size: {len(raw)}')

if raw:
    print(f'Stream premiers 16 bytes: {raw[:16].hex()}')
else:
    print('Stream: VIDE')

for wb in [15, -15, 47]:
    try:
        d = zlib.decompress(raw, wbits=wb)
        print(f'wbits={wb}: OK -> {len(d)} octets')
        break
    except Exception as e:
        print(f'wbits={wb}: FAIL -> {e}')
