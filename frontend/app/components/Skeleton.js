export default function Skeleton({ className = '', ...props }) {
  return (
    <div 
      className={`relative overflow-hidden bg-accent/50 rounded-xl ${className}`} 
      {...props} 
    >
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/10 dark:via-white/5 to-transparent" />
    </div>
  );
}

export function SkeletonText({ lines = 3, className = '' }) {
  return (
    <div className={`space-y-4 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton 
          key={i} 
          className={`h-3 ${i === lines - 1 ? 'w-2/3' : 'w-full'} rounded-full`} 
        />
      ))}
    </div>
  );
}

export function SkeletonCard({ className = '' }) {
  return (
    <div className={`p-6 glass rounded-2xl border border-border space-y-6 ${className}`}>
        <div className="flex items-center gap-4">
            <Skeleton className="w-12 h-12 rounded-2xl" />
            <div className="space-y-3 flex-1">
                <Skeleton className="h-4 w-1/3 rounded-full" />
                <Skeleton className="h-3 w-1/4 rounded-full opacity-60" />
            </div>
        </div>
        <SkeletonText lines={2} />
    </div>
  );
}
