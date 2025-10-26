import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Scatter, ScatterChart } from 'recharts'
import { format } from 'date-fns'
import { TimeseriesPoint } from '@/types'
import { formatDuration } from '@/utils/format'

interface BuildTimeChartProps {
  data: TimeseriesPoint[]
}

export default function BuildTimeChart({ data }: BuildTimeChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="w-full h-80 flex items-center justify-center text-gray-500">
        No build data available
      </div>
    )
  }

  const chartData = data.map(point => ({
    timestamp: new Date(point.timestamp).getTime(),
    duration: point.duration_seconds,
    success: point.success,
    commit: point.commit_sha.substring(0, 7),
  }))

  // Filter out builds with null or negative durations
  const successData = chartData.filter(d => d.success && d.duration !== null && d.duration >= 0)
  const failureData = chartData.filter(d => !d.success && d.duration !== null && d.duration >= 0)

  if (successData.length === 0 && failureData.length === 0) {
    return (
      <div className="w-full h-80 flex items-center justify-center text-gray-500">
        No build time data available
      </div>
    )
  }

  return (
    <div className="w-full h-80">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(timestamp) => format(new Date(timestamp), 'MMM d')}
            label={{ value: 'Date', position: 'insideBottom', offset: -10 }}
          />
          <YAxis
            dataKey="duration"
            type="number"
            domain={[0, 'dataMax']}
            tickFormatter={(value) => formatDuration(value)}
            label={{ value: 'Build Time', angle: -90, position: 'insideLeft' }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload || payload.length === 0) return null
              const data = payload[0].payload
              return (
                <div className="bg-white p-3 border border-gray-200 rounded shadow-lg">
                  <p className="font-semibold">{format(new Date(data.timestamp), 'PPpp')}</p>
                  {data.duration !== null && (
                    <p className="text-sm">Duration: {formatDuration(data.duration)}</p>
                  )}
                  <p className="text-sm">Commit: {data.commit}</p>
                  <p className={`text-sm font-medium ${data.success ? 'text-green-600' : 'text-red-600'}`}>
                    {data.success ? 'Success' : 'Failed'}
                  </p>
                </div>
              )
            }}
          />
          {successData.length > 0 && (
            <Scatter
              name="Successful Builds"
              data={successData}
              fill="#10b981"
              shape="circle"
              r={4}
            />
          )}
          {failureData.length > 0 && (
            <Scatter
              name="Failed Builds"
              data={failureData}
              fill="#ef4444"
              shape="circle"
              r={4}
            />
          )}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
