"""Quick check: how many technique embeddings are indexed, and is retrieval stable?"""
import sys, asyncio
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mental_health_wellness.memory.pgvector_store import _query, TABLE_NAME, search_embeddings


async def main():
    # 1. Count indexed technique embeddings
    rows = await _query(f'SELECT COUNT(*) AS n FROM {TABLE_NAME} WHERE "sourceType" = \'technique\'')
    n_tech = rows[0]["n"] if rows else "?"
    total = await _query(f'SELECT "sourceType", COUNT(*) AS n FROM {TABLE_NAME} GROUP BY "sourceType"')
    print(f"\nIndexed technique embeddings: {n_tech}")
    print("By source type:")
    for r in (total or []):
        print(f"   {r['sourceType']:<12} {r['n']}")

    # 2. Stability: same structured anger query 3x, count rows each time
    q = ("emotion: anger | intensity: 0.85 | primary feeling: anger | "
         "secondary feelings: feeling_disrespected, irritability | symptoms: body_tension")
    print("\nRetrieval stability (same query x3, limit=10):")
    for i in range(3):
        res = await search_embeddings(query=q, source_types=["technique"], limit=10)
        top = f"{float(res[0].get('similarity') or 0):.3f}" if res else "—"
        print(f"   run {i+1}: {len(res)} rows returned, top_sim={top}")
        await asyncio.sleep(1.0)


if __name__ == "__main__":
    asyncio.run(main())
