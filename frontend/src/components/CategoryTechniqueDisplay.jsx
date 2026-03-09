import React, { useState } from 'react';
import TechniqueCard from './TechniqueCard';

export default function CategoryTechniqueDisplay({ techniquesByCategory, userId }) {
  const categories = Object.keys(techniquesByCategory);
  const [selectedCategory, setSelectedCategory] = useState(categories[0] || null);

  console.log('[CategoryTechniqueDisplay] Received:', { techniquesByCategory, categories, selectedCategory });

  if (categories.length === 0) {
    console.log('[CategoryTechniqueDisplay] No categories - returning null');
    return null;
  }

  const selectedTechnique = techniquesByCategory[selectedCategory];

  const categoryEmojis = {
    'Breathing': '🌬️',
    'Mindfulness': '🧘',
    'CBT': '🧠',
    'DBT': '⚖️',
    'Journaling': '📝',
    'Behavioral Activation': '🏃'
  };

  const categoryColors = {
    'Breathing': 'from-cyan-100 to-blue-100',
    'Mindfulness': 'from-purple-100 to-indigo-100',
    'CBT': 'from-indigo-100 to-purple-100',
    'DBT': 'from-pink-100 to-rose-100',
    'Journaling': 'from-blue-100 to-cyan-100',
    'Behavioral Activation': 'from-orange-100 to-red-100'
  };

  const categoryButtonColors = {
    'Breathing': 'bg-cyan-500 hover:bg-cyan-600',
    'Mindfulness': 'bg-purple-500 hover:bg-purple-600',
    'CBT': 'bg-indigo-500 hover:bg-indigo-600',
    'DBT': 'bg-pink-500 hover:bg-pink-600',
    'Journaling': 'bg-blue-500 hover:bg-blue-600',
    'Behavioral Activation': 'bg-orange-500 hover:bg-orange-600'
  };

  return (
    <div className="flex justify-start animate-slide-up mb-6 px-1">
      <div className="w-full max-w-3xl">
        {/* Category Header */}
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Healing Exercises for Your Emotions:</h3>
        </div>

        {/* Category Tabs/Buttons */}
        <div className="flex flex-wrap gap-2 mb-6 pb-4 border-b-2 border-gray-200">
          {categories.map((category) => {
            const isSelected = selectedCategory === category;
            const buttonColor = categoryButtonColors[category] || 'bg-gray-500';
            
            return (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-4 py-2.5 rounded-lg font-semibold transition-all duration-200 text-sm ${
                  isSelected
                    ? `${buttonColor} text-white shadow-lg scale-105`
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200 shadow'
                }`}
              >
                <span className="mr-2">{categoryEmojis[category]}</span>
                {category}
              </button>
            );
          })}
        </div>

        {/* Technique Card */}
        {selectedTechnique && (
          <div className={`rounded-xl p-6 bg-gradient-to-br ${categoryColors[selectedCategory] || 'from-gray-50 to-gray-100'}`}>
            <TechniqueCard
              technique={selectedTechnique}
              userId={userId}
            />
          </div>
        )}
      </div>
    </div>
  );
}
