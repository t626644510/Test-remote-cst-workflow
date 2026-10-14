"""Read the validated CST binary tensor format; not a CST API or general reader.

Fail-closed format checks: fixed tensor marker, float width, three exact node
counts, bounded LZ4 blocks, exact decompressed lengths, finite values, no
unparsed trailing bytes. Tensor physical meaning must be checked separately.
"""
from pathlib import Path
import struct,json,hashlib
import numpy as np

def lz4_block(src,expected):
    out=bytearray();i=0
    while i<len(src):
        token=src[i];i+=1;n=token>>4
        if n==15:
            while True:
                v=src[i];i+=1;n+=v
                if v!=255:break
        assert i+n<=len(src)
        out.extend(src[i:i+n]);i+=n
        if i==len(src):break
        off=struct.unpack_from('<H',src,i)[0];i+=2
        assert 0<off<=len(out)
        n=(token&15)+4
        if (token&15)==15:
            while True:
                v=src[i];i+=1;n+=v
                if v!=255:break
        assert len(out)+n<=expected
        pattern=out[-off:]
        out.extend(pattern*(n//off)+pattern[:n%off])
    assert len(out)==expected
    return bytes(out)

def read_tensor(path,N):
    b=path.read_bytes()
    assert b.startswith(b'\x0a\x00\x00\x00CST Tensor') and b[22:27]==b'float'
    marker=bytes.fromhex('ae523301');offset=b.index(marker)+4
    arrays=[];audit=[]
    for d in range(3):
        n,blocks,chunk=struct.unpack_from('<QQQ',b,offset);offset+=24
        assert n==N and blocks==(4*N+chunk-1)//chunk and chunk==1048576
        raw=bytearray()
        for k in range(blocks):
            size,rawsize=struct.unpack_from('<QQ',b,offset);offset+=16
            assert 0<size<len(b) and 0<rawsize<=chunk
            raw.extend(lz4_block(b[offset:offset+size],rawsize));offset+=size
        assert len(raw)==4*N
        a=np.frombuffer(raw,dtype='<f4').copy();assert np.all(np.isfinite(a))
        arrays.append(a)
        audit.append(dict(min=float(a.min()),max=float(a.max()),nonzero=int(np.count_nonzero(a))))
    assert offset==len(b),(offset,len(b))
    return np.array(arrays),dict(source_sha256=hashlib.sha256(b).hexdigest(),components=audit,all_bytes_consumed=True)
