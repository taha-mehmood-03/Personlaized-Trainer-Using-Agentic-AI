import React, { useState, useEffect } from 'react'
import { ArrowLeft, Trash2, Download, Calendar, Brain, TrendingUp } from 'lucide-react'

const API_URL = 'http://localhost:5000/api'

export default function HistoryPage({ userId, onBack }) {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all') // 'all', 'positive', 'negative', 'neutral'

  useEffect(() => {
    loadHistory()
  }, [userId])

  const loadHistory = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_URL}/user/${userId}/history`)
      const data = await response.json()
      
      if (data.status === 'success') {
        setHistory(data.history)
      }
    } catch (error) {
      console.error('Error loading history:', error)
    } finally {
      setLoading(false)
    }
  }

  const deleteAnalysis = (analysisId) => {
    setHistory(history.filter(item => item.id !== analysisId))
  }

  const filteredHistory = history.filter(item => {
    if (filter === 'all') return true
    return item.sentiment === filter
  })

  // Normalize old "comprehensive" entries to show as one of the individual methods
  const normalizedHistory = filteredHistory.map(item => {
    if (item.method === 'comprehensive') {
      // Show old comprehensive entries as VADER for clarity
      return { ...item, method: 'vader (legacy)' }
    }
    return item
  })

  const getSentimentColor = (sentiment) => {
    switch (sentiment) {
      case 'positive':
        return 'bg-green-50 border-green-200 text-green-700'
      case 'negative':
        return 'bg-red-50 border-red-200 text-red-700'
      case 'neutral':
        return 'bg-gray-50 border-gray-200 text-gray-700'
      default:
        return 'bg-blue-50 border-blue-200 text-blue-700'
    }
  }

  const getSentimentIcon = (sentiment) => {
    switch (sentiment) {
      case 'positive':
        return '😊'
      case 'negative':
        return '😔'
      case 'neutral':
        return '😐'
      default:
        return '🤔'
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-teal-50 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button
            onClick={onBack}
            className="p-2 hover:bg-white rounded-lg transition-colors"
          >
            <ArrowLeft className="w-6 h-6 text-gray-700" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-800">Analysis History</h1>
            <p className="text-gray-600 mt-1">View and manage your sentiment analysis records</p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-lg p-4 border border-gray-200 shadow-sm">
            <p className="text-gray-600 text-sm font-semibold">Total Analyses</p>
            <p className="text-2xl font-bold text-gray-800 mt-1">{history.length}</p>
          </div>
          <div className="bg-white rounded-lg p-4 border border-green-200 shadow-sm">
            <p className="text-green-600 text-sm font-semibold">Positive</p>
            <p className="text-2xl font-bold text-green-700 mt-1">
              {history.filter(h => h.sentiment === 'positive').length}
            </p>
          </div>
          <div className="bg-white rounded-lg p-4 border border-red-200 shadow-sm">
            <p className="text-red-600 text-sm font-semibold">Negative</p>
            <p className="text-2xl font-bold text-red-700 mt-1">
              {history.filter(h => h.sentiment === 'negative').length}
            </p>
          </div>
          <div className="bg-white rounded-lg p-4 border border-gray-200 shadow-sm">
            <p className="text-gray-600 text-sm font-semibold">Neutral</p>
            <p className="text-2xl font-bold text-gray-700 mt-1">
              {history.filter(h => h.sentiment === 'neutral').length}
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-lg p-4 mb-6 border border-gray-200 shadow-sm">
          <p className="text-sm font-semibold text-gray-700 mb-3">Filter by Sentiment:</p>
          <div className="flex gap-2 flex-wrap">
            {['all', 'positive', 'negative', 'neutral'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-4 py-2 rounded-lg font-medium transition-all capitalize ${
                  filter === f
                    ? 'bg-purple-500 text-white shadow-md'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {/* History List */}
        {loading ? (
          <div className="text-center py-12">
            <p className="text-gray-600">Loading history...</p>
          </div>
        ) : filteredHistory.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
            <Brain className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600 font-medium">No analyses found</p>
            <p className="text-gray-500 text-sm mt-1">Start analyzing your mood to build history</p>
          </div>
        ) : (
          <div className="space-y-4">
            {normalizedHistory.map((item, index) => (
              <div
                key={item.id}
                className={`border rounded-lg p-4 shadow-sm hover:shadow-md transition-all ${getSentimentColor(
                  item.sentiment
                )}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-2xl">{getSentimentIcon(item.sentiment)}</span>
                      <div>
                        <p className="font-semibold capitalize">
                          {item.sentiment} Sentiment
                        </p>
                        <p className="text-xs opacity-75 flex items-center gap-1 mt-1">
                          <Calendar className="w-3 h-3" />
                          {new Date(item.timestamp).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <p className="text-sm line-clamp-2 mt-3 opacity-90">{item.text}</p>
                    <div className="flex items-center gap-4 mt-3 text-xs opacity-75">
                      <span className="bg-white bg-opacity-50 px-2 py-1 rounded">
                        Method: <span className="font-semibold">{item.method}</span>
                      </span>
                      <span className="bg-white bg-opacity-50 px-2 py-1 rounded">
                        Confidence: <span className="font-semibold">{(item.confidence * 100).toFixed(1)}%</span>
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-2 ml-4">
                    <button
                      onClick={() => {
                        // Copy to clipboard
                        navigator.clipboard.writeText(item.text)
                      }}
                      className="p-2 hover:bg-white hover:bg-opacity-50 rounded transition-colors"
                      title="Copy text"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => deleteAnalysis(item.id)}
                      className="p-2 hover:bg-white hover:bg-opacity-50 rounded transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
