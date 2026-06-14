const statSkeletons = Array.from({ length: 5 })
const panelSkeletons = Array.from({ length: 4 })

export default function DashboardLoading() {
  return (
    <main className="space-y-6 pb-10">
      <header className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="space-y-3">
            <div className="h-6 w-44 animate-pulse rounded-full bg-slate-100" />
            <div className="h-8 w-64 animate-pulse rounded-lg bg-slate-100" />
            <div className="h-4 w-80 max-w-full animate-pulse rounded bg-slate-100" />
          </div>
          <div className="grid grid-cols-3 gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3">
            {[1, 2, 3].map((item) => (
              <div key={item} className="h-11 w-24 animate-pulse rounded-lg bg-white" />
            ))}
          </div>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {statSkeletons.map((_, index) => (
          <div key={index} className="h-32 animate-pulse rounded-xl border border-slate-200 bg-white shadow-sm" />
        ))}
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="h-80 animate-pulse rounded-xl border border-slate-200 bg-white shadow-sm xl:col-span-2" />
        <div className="h-80 animate-pulse rounded-xl border border-slate-200 bg-white shadow-sm" />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {panelSkeletons.map((_, index) => (
          <div key={index} className="h-72 animate-pulse rounded-xl border border-slate-200 bg-white shadow-sm" />
        ))}
      </section>
    </main>
  )
}
