from nacl.signing import SigningKey
import base64, os

OUT = ".env"
if os.path.exists(OUT):
    print(".env already exists. Delete it if you want to regenerate.")
    raise SystemExit(0)

sk = SigningKey.generate()  # 32-byte secret seed
vk = sk.verify_key

seed_b64 = base64.b64encode(sk.encode()).decode()  # 32 bytes
pub_b64 = base64.b64encode(bytes(vk)).decode()  # 32 bytes

with open(OUT, "w") as f:
    f.write(f"SWARM_SIGNING_SK_B64={seed_b64}\n")
    f.write(f"SWARM_VERIFY_PK_B64={pub_b64}\n")

print("Wrote .env with SWARM_SIGNING_SK_B64 and SWARM_VERIFY_PK_B64")
