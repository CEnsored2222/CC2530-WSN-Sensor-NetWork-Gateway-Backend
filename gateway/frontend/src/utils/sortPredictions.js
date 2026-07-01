/**
 * 预测值键排序工具
 * 后端返回 predicted_values 键如 "t+10","t+20","t+120"
 * 必须按数值排序,不能按字符串排序(否则 "t+120" 会排在 "t+20" 前面)
 *
 * @param {Object} predictedValues - { "t+10": 25.3, "t+20": 26.1, ... }
 * @returns {Array<{step:number, value:number}>} 按 step 升序排列
 */
export function sortPredictions(predictedValues) {
  if (!predictedValues || typeof predictedValues !== 'object') return []
  return Object.entries(predictedValues)
    .map(([key, value]) => {
      const step = parseInt(String(key).replace('t+', ''), 10)
      return { step: isNaN(step) ? 0 : step, value, key }
    })
    .sort((a, b) => a.step - b.step)
}

/**
 * 仅返回排序后的步长数组(用于图表 X 轴)
 */
export function sortedSteps(predictedValues) {
  return sortPredictions(predictedValues).map((p) => p.step)
}
