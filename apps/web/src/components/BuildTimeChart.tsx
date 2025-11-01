import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { format } from 'date-fns'
import { TimeseriesPoint } from '@/types'
import { formatDuration } from '@/utils/format'

interface BuildTimeChartProps {
  data: TimeseriesPoint[]
}

export default function BuildTimeChart({ data }: BuildTimeChartProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)
  const legendRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const selectedIdxRef = useRef<number | null>(null)
  const globalClickHandlerRef = useRef<((e: MouseEvent) => void) | null>(null)

  useEffect(() => {
    if (!chartRef.current || !data || data.length === 0) return

    // Create tooltip and prepend to body (so it's on top)
    if (!tooltipRef.current) {
      const tooltipDiv = document.createElement('div')
      tooltipDiv.id = 'uplot-tooltip'
      tooltipDiv.style.position = 'fixed'
      tooltipDiv.style.display = 'none'
      tooltipDiv.style.pointerEvents = 'auto'
      tooltipDiv.style.zIndex = '999999'
      document.body.insertBefore(tooltipDiv, document.body.firstChild)
      tooltipRef.current = tooltipDiv
    }

    // Filter and separate success/failure data
    const validData = data.filter(d => d.duration_seconds !== null && d.duration_seconds >= 0)

    if (validData.length === 0) return

    // Sort by timestamp
    validData.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

    // Prepare data for uPlot: [timestamps, success_durations, failure_durations]
    const timestamps: number[] = []
    const successDurations: (number | null)[] = []
    const failureDurations: (number | null)[] = []
    let successCount = 0
    let failureCount = 0

    // Store original data points for tooltip access
    const dataPoints: TimeseriesPoint[] = []

    validData.forEach(point => {
      const ts = Math.floor(new Date(point.timestamp).getTime() / 1000) // uPlot uses seconds
      timestamps.push(ts)
      dataPoints.push(point)

      if (point.success) {
        successDurations.push(point.duration_seconds)
        failureDurations.push(null)
        successCount++
      } else {
        successDurations.push(null)
        failureDurations.push(point.duration_seconds)
        failureCount++
      }
    })

    const plotData: uPlot.AlignedData = [
      timestamps,
      successDurations,
      failureDurations,
    ]

    const opts: uPlot.Options = {
      width: chartRef.current.offsetWidth,
      height: 320,
      padding: [16, 16, 0, 16],  // Added left padding to make first/last points clickable
      legend: {
        show: false, // We'll create a custom legend
      },
      cursor: {
        points: {
          size: 12,
          width: 3,
        },
        drag: {
          x: false,
          y: false,
        },
        focus: {
          prox: 30, // Increase proximity radius to make points easier to click
        },
      },
      hooks: {
        init: [
          (u) => {
            // Add click handler to the overlay canvas
            const over = u.root.querySelector('.u-over') as HTMLElement
            if (!over) return

            // Global click handler to close tooltip when clicking outside
            const handleGlobalClick = (e: MouseEvent) => {
              if (!tooltipRef.current || tooltipRef.current.style.display === 'none') return

              // Don't close if clicking on the tooltip itself
              if (tooltipRef.current.contains(e.target as Node)) return

              // Close the tooltip
              tooltipRef.current.style.display = 'none'
              selectedIdxRef.current = null
            }

            globalClickHandlerRef.current = handleGlobalClick
            document.addEventListener('click', handleGlobalClick)

            over.addEventListener('click', (e) => {
              e.stopPropagation() // Prevent global handler from firing immediately

              if (!tooltipRef.current) return

              const idx = u.cursor.idx
              console.log(`Chart clicked - cursor.idx: ${idx}, total points: ${dataPoints.length}`)

              if (idx === null || idx === undefined) {
                // Clicked on chart but not near a point - close tooltip
                console.log('No point found near click')
                tooltipRef.current.style.display = 'none'
                selectedIdxRef.current = null
                return
              }

              const point = dataPoints[idx]
              console.log(`Point at idx ${idx}:`, point ? `${point.success ? 'SUCCESS' : 'FAILURE'} - ${point.commit_sha.substring(0, 7)}` : 'NOT FOUND')
              if (!point) return

              // If clicking the same point, hide tooltip
              if (idx === selectedIdxRef.current) {
                tooltipRef.current.style.display = 'none'
                selectedIdxRef.current = null
                return
              }

              // Store selected index
              selectedIdxRef.current = idx

              // Get cursor position
              const left = u.cursor.left
              const top = u.cursor.top

              if (left === null || top === null) return

              const bbox = u.bbox
              const canvasRect = over.getBoundingClientRect()

              // Position and show tooltip
              const tooltip = tooltipRef.current

              // Update tooltip content
              tooltip.innerHTML = `
                <div style="background: white; border: 2px solid ${point.success ? '#10b981' : '#ef4444'}; border-radius: 0.5rem; padding: 0.75rem; box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1); font-size: 0.875rem; min-width: 200px; max-width: 300px; position: relative;">
                  <button
                    id="close-tooltip-btn"
                    style="
                      position: absolute;
                      top: 0.5rem;
                      right: 0.5rem;
                      background: transparent;
                      border: none;
                      color: #ef4444;
                      font-size: 1.25rem;
                      line-height: 1;
                      cursor: pointer;
                      padding: 0;
                      width: 20px;
                      height: 20px;
                      display: flex;
                      align-items: center;
                      justify-content: center;
                    "
                    onmouseover="this.style.color='#dc2626'"
                    onmouseout="this.style.color='#ef4444'"
                  >
                    ×
                  </button>
                  <div style="font-weight: 600; margin-bottom: 0.5rem; padding-right: 1.5rem;">${format(new Date(point.timestamp), 'PPpp')}</div>
                  <div style="margin-bottom: 0.25rem;">Duration: ${formatDuration(point.duration_seconds!)}</div>
                  <div style="margin-bottom: 0.25rem;">Commit: <span style="font-family: monospace;">${point.commit_sha.substring(0, 7)}</span></div>
                  ${point.commit_message ? `
                    <div style="margin-bottom: 0.5rem; color: #6b7280; font-size: 0.8125rem; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; line-height: 1.3;">${point.commit_message}</div>
                  ` : ''}
                  <div style="font-weight: 500; color: ${point.success ? '#059669' : '#dc2626'}; margin-bottom: 0.75rem;">${point.success ? '✓ Success' : '✗ Failed'}</div>
                  ${point.build_url ? `
                    <button
                      id="view-build-btn"
                      style="
                        width: 100%;
                        background: #2563eb;
                        color: white;
                        padding: 0.5rem;
                        border: none;
                        border-radius: 0.375rem;
                        font-size: 0.875rem;
                        font-weight: 500;
                        cursor: pointer;
                        transition: background 0.2s;
                      "
                      onmouseover="this.style.background='#1d4ed8'"
                      onmouseout="this.style.background='#2563eb'"
                    >
                      View Build →
                    </button>
                  ` : ''}
                </div>
              `

              // Show and position it at the cursor
              tooltip.style.display = 'block'

              // Calculate position - check if it would overflow to the right
              const tooltipWidth = 300 // max-width of tooltip
              const cursorX = canvasRect.left + left
              const cursorY = canvasRect.top + top

              // Check if tooltip would overflow right edge of viewport
              const wouldOverflowRight = (cursorX + 10 + tooltipWidth) > window.innerWidth

              if (wouldOverflowRight) {
                // Position to the left of cursor
                tooltip.style.left = `${cursorX - tooltipWidth - 10}px`
              } else {
                // Position to the right of cursor
                tooltip.style.left = `${cursorX + 10}px`
              }

              tooltip.style.top = `${cursorY + 10}px`

              // Add click handler to close button
              const closeBtn = tooltip.querySelector('#close-tooltip-btn')
              if (closeBtn) {
                closeBtn.addEventListener('click', (e) => {
                  e.stopPropagation()
                  tooltip.style.display = 'none'
                  selectedIdxRef.current = null
                })
              }

              // Add click handler to view build button
              if (point.build_url) {
                const btn = tooltip.querySelector('#view-build-btn')
                if (btn) {
                  btn.addEventListener('click', (e) => {
                    e.stopPropagation()
                    window.open(point.build_url!, '_blank', 'noopener,noreferrer')
                  })
                }
              }
            })
          }
        ]
      },
      series: [
        {
          label: 'Time',
        },
        {
          label: 'Successful Builds',
          stroke: 'transparent',
          width: 0,
          points: {
            show: true,
            size: 5,
            stroke: '#10b981',
            fill: '#10b981',
          },
        },
        {
          label: 'Failed Builds',
          stroke: 'transparent',
          width: 0,
          points: {
            show: true,
            size: 5,
            stroke: '#ef4444',
            fill: '#ef4444',
          },
        },
      ],
      axes: [
        {
          label: 'Date',
          space: 60,
          values: (u, vals) => vals.map(v => format(new Date(v * 1000), 'MMM d')),
        },
        {
          label: 'Build Time',
          space: 60,
          values: (u, vals) => vals.map(v => formatDuration(v)),
          side: 3,
        },
      ],
      scales: {
        x: {
          time: true,
        },
        y: {
          range: (u, dataMin, dataMax) => {
            return [0, dataMax * 1.1] // Add 10% padding at top
          },
        },
      },
    }

    // Create the plot
    plotRef.current = new uPlot(opts, plotData, chartRef.current)

    // Update custom legend
    if (legendRef.current) {
      legendRef.current.innerHTML = `
        <div style="display: flex; justify-content: center; gap: 2rem; margin-top: 1rem; font-size: 0.875rem;">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <div style="width: 12px; height: 12px; background-color: #10b981; border-radius: 2px;"></div>
            <span>Successful Builds: ${successCount}</span>
          </div>
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <div style="width: 12px; height: 12px; background-color: #ef4444; border-radius: 2px;"></div>
            <span>Failed Builds: ${failureCount}</span>
          </div>
        </div>
      `
    }

    // Handle window resize
    const handleResize = () => {
      if (plotRef.current && chartRef.current) {
        plotRef.current.setSize({ width: chartRef.current.offsetWidth, height: 320 })
      }
    }

    window.addEventListener('resize', handleResize)

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize)
      if (globalClickHandlerRef.current) {
        document.removeEventListener('click', globalClickHandlerRef.current)
        globalClickHandlerRef.current = null
      }
      if (plotRef.current) {
        plotRef.current.destroy()
        plotRef.current = null
      }
      if (tooltipRef.current) {
        document.body.removeChild(tooltipRef.current)
        tooltipRef.current = null
      }
    }
  }, [data])

  if (!data || data.length === 0) {
    return (
      <div className="w-full h-80 flex items-center justify-center text-gray-500">
        No build data available
      </div>
    )
  }

  const validData = data.filter(d => d.duration_seconds !== null && d.duration_seconds >= 0)

  if (validData.length === 0) {
    return (
      <div className="w-full h-80 flex items-center justify-center text-gray-500">
        No build time data available
      </div>
    )
  }

  return (
    <div className="w-full" style={{ position: 'relative' }}>
      <div ref={chartRef} />
      <div ref={legendRef} />
    </div>
  )
}
