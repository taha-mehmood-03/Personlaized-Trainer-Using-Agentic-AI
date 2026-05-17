import asyncio
from prisma import Prisma

async def main():
    p = Prisma()
    await p.connect()
    users = await p.user.find_many()
    print([u.id for u in users])
    await p.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
