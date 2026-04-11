export default function RootLoading() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-50">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500 to-teal-400 p-0.5 animate-pulse">
          <div className="w-full h-full bg-white rounded-2xl flex items-center justify-center">
            <span className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-teal-500">S</span>
          </div>
        </div>
        <p className="text-sm font-semibold text-slate-500 uppercase tracking-widest">Loading...</p>
      </div>
    </div>
  )
}
