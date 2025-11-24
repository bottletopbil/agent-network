import asyncio
import os
from nats.aio.client import Client as NATS

async def main():
    nc = NATS()
    await nc.connect(servers=["nats://127.0.0.1:4222"])
    js = nc.jetstream()
    
    stream = "THREADS"
    
    # List all consumers
    consumers = await js.consumers_info(stream)
    for consumer in consumers:
        name = consumer.name
        try:
            await js.delete_consumer(stream, name)
            print(f"Deleted consumer {name}")
        except Exception as e:
            print(f"Error deleting consumer {name}: {e}")
        
    await nc.close()

if __name__ == "__main__":
    asyncio.run(main())
