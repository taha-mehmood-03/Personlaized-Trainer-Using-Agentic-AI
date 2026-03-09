import React, { useState } from 'react'
import { Star, Clock, Zap, ChevronDown, ChevronUp, AlertCircle, BookOpen, Lightbulb, Check } from 'lucide-react'

const API_URL = 'http://localhost:8000/api'

export default function TechniqueCard({ technique, userId, onRatingSubmitted }) {
  const [expanded, setExpanded] = useState(false)
  const [userRating, setUserRating] = useState(0)
  const [hoverRating, setHoverRating] = useState(0)
  const [feedback, setFeedback] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)
  const [hoverCard, setHoverCard] = useState(false)

  const handleSubmitRating = async () => {
    if (userRating === 0) {
      setError('Please select a rating')
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const response = await fetch(`${API_URL}/technique/rate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: userId,
          technique_id: technique.id,
          rating: userRating,
          feedback: feedback || null,
          completed: true
        })
      })

      const data = await response.json()

      if (data.status === 'success') {
        setSubmitted(true)
        setUserRating(0)
        setFeedback('')
        if (onRatingSubmitted) {
          onRatingSubmitted(technique.id, userRating)
        }
        // Reset submitted state after 3 seconds
        setTimeout(() => setSubmitted(false), 3000)
      } else {
        setError(data.message || 'Failed to submit rating')
      }
    } catch (error) {
      console.error('Error submitting rating:', error)
      setError('Error submitting rating. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const getDifficultyColor = (difficulty) => {
    switch (difficulty?.toLowerCase()) {
      case 'easy':
        return 'bg-green-100 text-green-800'
      case 'moderate':
        return 'bg-yellow-100 text-yellow-800'
      case 'hard':
        return 'bg-red-100 text-red-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getDifficultyEmoji = (difficulty) => {
    switch (difficulty?.toLowerCase()) {
      case 'easy':
        return '😌'
      case 'moderate':
        return '🎯'
      case 'hard':
        return '💪'
      default:
        return '📝'
    }
  }

  const getCategoryColor = (category) => {
    const colors = {
      breathing: 'from-cyan-400 to-blue-500',
      meditation: 'from-purple-400 to-indigo-500',
      mindfulness: 'from-green-400 to-teal-500',
      grounding: 'from-orange-400 to-red-500',
      progressive: 'from-pink-400 to-rose-500',
      visualization: 'from-yellow-400 to-orange-400',
      cbt: 'from-indigo-400 to-purple-500',
      journaling: 'from-blue-400 to-cyan-500',
    }
    return colors[category?.toLowerCase()] || 'from-purple-400 to-teal-500'
  }

  return (
    <div 
      className="bg-gradient-to-br from-white to-gray-50 border-2 border-gray-200 rounded-2xl overflow-hidden shadow-md hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1"
      onMouseEnter={() => setHoverCard(true)}
      onMouseLeave={() => setHoverCard(false)}
    >
      {/* Header with Gradient Background */}
      <div className={`p-5 bg-gradient-to-r ${getCategoryColor(technique.category)} text-white relative overflow-hidden`}>
        {/* Decorative Background Element */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16"></div>
        
        <div className="flex items-start justify-between gap-4 relative z-10">
          <div className="flex-1">
            <div className="flex items-start gap-2">
              <span className="text-3xl mt-1">{technique.category === 'breathing' ? '🌬️' : technique.category === 'meditation' ? '🧘' : technique.category === 'mindfulness' ? '🌿' : '✨'}</span>
              <div>
                <h3 className="text-lg font-bold mb-1">{technique.name}</h3>
                <p className="text-sm opacity-90 line-clamp-2">{technique.brief}</p>
              </div>
            </div>
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-2 hover:bg-white/20 rounded-lg transition-all hover:scale-110 active:scale-95 flex-shrink-0"
          >
            {expanded ? (
              <ChevronUp className="w-6 h-6" />
            ) : (
              <ChevronDown className="w-6 h-6" />
            )}
          </button>
        </div>

        {/* Quick Info Pills */}
        <div className="flex flex-wrap gap-2 mt-4 relative z-10">
          {/* Duration */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white/20 backdrop-blur-sm rounded-full hover:bg-white/30 transition-all">
            <Clock className="w-4 h-4" />
            <span className="text-xs font-medium">{technique.duration_minutes} min</span>
          </div>

          {/* Difficulty */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white/20 backdrop-blur-sm rounded-full hover:bg-white/30 transition-all">
            <span className="text-sm">{getDifficultyEmoji(technique.difficulty)}</span>
            <span className="text-xs font-medium capitalize">{technique.difficulty || 'Moderate'}</span>
          </div>

          {/* Category Badge */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white/20 backdrop-blur-sm rounded-full hover:bg-white/30 transition-all">
            <Zap className="w-4 h-4" />
            <span className="text-xs font-medium capitalize">{technique.category}</span>
          </div>
        </div>

        {/* Rating Display */}
        {technique.avg_rating > 0 && (
          <div className="flex items-center gap-3 mt-4 relative z-10">
            <div className="flex items-center gap-1">
              {[...Array(5)].map((_, i) => (
                <Star
                  key={i}
                  className={`w-4 h-4 transition-all ${i < Math.round(technique.avg_rating)
                    ? 'fill-white text-white'
                    : 'text-white/40'
                    }`}
                />
              ))}
            </div>
            <span className="text-sm font-bold">{technique.avg_rating.toFixed(1)}/5</span>
            <span className="text-xs opacity-75">({Math.round(technique.effectiveness * 100)}% effective)</span>
          </div>
        )}
      </div>

      {/* Expanded Content */}
      {expanded && (
        <div className="p-6 space-y-6 border-t border-gray-200 animate-slide-down">
          {/* Full Description */}
          {technique.description && (
            <div className="bg-gradient-to-br from-slate-50 to-blue-50 p-4 rounded-xl border border-blue-200">
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="w-5 h-5 text-blue-600" />
                <h4 className="text-sm font-bold text-gray-900">About This Technique</h4>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed">{technique.description}</p>
            </div>
          )}

          {/* Why It Works */}
          {technique.why_it_works && (
            <div className="bg-gradient-to-br from-purple-50 to-pink-50 p-4 rounded-xl border border-purple-200">
              <div className="flex items-center gap-2 mb-2">
                <Lightbulb className="w-5 h-5 text-purple-600" />
                <h4 className="text-sm font-bold text-gray-900">Why It Works</h4>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed">{technique.why_it_works}</p>
            </div>
          )}

          {/* Steps */}
          {technique.steps && technique.steps.length > 0 && (
            <div className="bg-gradient-to-br from-teal-50 to-green-50 p-4 rounded-xl border border-teal-200">
              <h4 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
                <span className="text-2xl">📋</span> How to Practice
              </h4>
              <ol className="space-y-3">
                {technique.steps.map((step, index) => (
                  <li key={index} className="flex gap-3">
                    <span className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-purple-500 to-teal-500 text-white flex items-center justify-center text-xs font-bold">
                      {index + 1}
                    </span>
                    <span className="text-sm text-gray-700 leading-relaxed pt-1">{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Effectiveness */}
          {technique.effectiveness && (
            <div className="bg-gradient-to-r from-indigo-50 to-purple-50 p-4 rounded-xl border border-indigo-200">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                  <span className="text-lg">📊</span> Effectiveness Score
                </h4>
                <span className="text-lg font-bold bg-gradient-to-r from-purple-600 to-teal-600 bg-clip-text text-transparent">
                  {(technique.effectiveness * 100).toFixed(0)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-purple-500 to-teal-500 h-2.5 rounded-full transition-all duration-500"
                  style={{ width: `${technique.effectiveness * 100}%` }}
                ></div>
              </div>
              <p className="text-xs text-gray-600 mt-2">Based on user feedback and clinical studies</p>
            </div>
          )}

          {/* Rating Section */}
          <div className="bg-gradient-to-br from-purple-50 to-teal-50 p-5 rounded-xl border-2 border-purple-200">
            <h4 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
              <span className="text-lg">💬</span> How helpful was this?
            </h4>

            {/* Error Message */}
            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex gap-2 animate-slide-down">
                <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-red-700">{error}</p>
              </div>
            )}

            {/* Success Message */}
            {submitted && (
              <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg animate-slide-down">
                <p className="text-xs font-bold text-green-700 flex items-center gap-2">
                  <Check className="w-4 h-4" /> Thank you for your feedback!
                </p>
              </div>
            )}

            {/* Star Rating */}
            <div className="flex gap-3 mb-4">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  onClick={() => setUserRating(star)}
                  onMouseEnter={() => setHoverRating(star)}
                  onMouseLeave={() => setHoverRating(0)}
                  className="transition-all hover:scale-125 active:scale-110 focus:outline-none"
                  disabled={submitting}
                  title={`Rate ${star} star${star !== 1 ? 's' : ''}`}
                >
                  <Star
                    className={`w-8 h-8 transition-all duration-200 ${
                      star <= (hoverRating || userRating)
                        ? 'fill-amber-400 text-amber-400 drop-shadow-lg'
                        : 'text-gray-300 hover:text-amber-200'
                    }`}
                  />
                </button>
              ))}
            </div>

            {/* Rating Text Display */}
            {(hoverRating || userRating) && (
              <div className="text-xs font-semibold text-purple-700 mb-3 animate-fade-in">
                {hoverRating || userRating} out of 5 stars
              </div>
            )}

            {/* Feedback Text */}
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Optional: Share your experience (e.g., helped me relax, easy to follow)"
              className="w-full px-4 py-3 text-sm border-2 border-gray-300 rounded-lg focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-200 resize-none transition-all bg-white/70"
              rows="2"
              disabled={submitting}
            />

            {/* Submit Button */}
            <button
              onClick={handleSubmitRating}
              disabled={submitting || submitted || userRating === 0}
              className={`w-full mt-4 py-3 rounded-lg font-bold text-sm transition-all duration-300 transform hover:scale-105 active:scale-95 ${
                submitted
                  ? 'bg-gradient-to-r from-green-500 to-teal-500 text-white'
                  : userRating === 0
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : 'bg-gradient-to-r from-purple-500 to-teal-500 text-white hover:shadow-lg'
              }`}
            >
              {submitting ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  Saving your feedback...
                </span>
              ) : submitted ? (
                <span className="flex items-center justify-center gap-2">
                  <Check className="w-4 h-4" /> Feedback Saved!
                </span>
              ) : (
                `Submit ${userRating > 0 ? `${userRating}-Star` : 'Your'} Rating`
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
