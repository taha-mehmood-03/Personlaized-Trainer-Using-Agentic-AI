const messageSkeletons = Array.from({ length: 4 })

export default function ChatLoading() {
  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-slate-50">
      <div className="h-9 shrink-0 animate-pulse bg-red-100" />
      <div className="flex min-h-0 flex-1 gap-3 overflow-hidden p-2 sm:p-3">
        <aside className="hidden w-72 shrink-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:block">
          <div className="border-b border-slate-100 p-4">
            <div className="h-10 w-40 animate-pulse rounded-xl bg-slate-100" />
          </div>
          <div className="space-y-3 p-3">
            {[1, 2, 3, 4, 5].map((item) => (
              <div key={item} className="h-14 animate-pulse rounded-xl bg-slate-100" />
            ))}
          </div>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex h-16 shrink-0 items-center border-b border-slate-200 px-4">
            <div className="h-8 w-56 animate-pulse rounded-lg bg-slate-100" />
          </div>

          <div className="custom-scrollbar flex-1 overflow-y-auto bg-slate-50 px-4 py-6">
            <div className="mx-auto flex max-w-4xl flex-col gap-4">
              <div className="h-24 animate-pulse rounded-xl border border-slate-200 bg-white shadow-sm" />
              {messageSkeletons.map((_, index) => (
                <div
                  key={index}
                  className={`h-20 w-4/5 animate-pulse rounded-2xl bg-white shadow-sm ${
                    index % 2 === 0 ? 'self-start' : 'self-end'
                  }`}
                />
              ))}
            </div>
          </div>

          <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-4">
            <div className="mx-auto h-20 max-w-4xl animate-pulse rounded-2xl bg-slate-100" />
          </div>
        </section>
      </div>
    </div>
  )
}
