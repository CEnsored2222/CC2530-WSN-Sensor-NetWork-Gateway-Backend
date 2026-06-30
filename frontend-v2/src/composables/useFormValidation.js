import { reactive, computed } from 'vue'

/**
 * 轻量表单验证 composable (不引入 vee-validate)
 *
 * const { errors, validate, touch } = useFormValidation(form, {
 *   name: [{ rule: 'required', msg: '必填' }, { rule: 'minLength:3', msg: '至少3字符' }],
 *   email: [{ rule: 'required', msg: '必填' }, { rule: 'email', msg: '邮箱格式错误' }]
 * })
 */
export function useFormValidation(form, rules) {
  const errors = reactive({})
  const touched = reactive({})

  function checkRule(value, ruleStr) {
    const [rule, param] = ruleStr.split(':')
    switch (rule) {
      case 'required':
        return value !== null && value !== undefined && String(value).trim() !== ''
      case 'email':
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
      case 'minLength':
        return String(value).length >= parseInt(param, 10)
      case 'maxLength':
        return String(value).length <= parseInt(param, 10)
      case 'min':
        return parseFloat(value) >= parseFloat(param)
      case 'max':
        return parseFloat(value) <= parseFloat(param)
      case 'phone':
        return /^1[3-9]\d{9}$/.test(value)
      case 'number':
        return !isNaN(parseFloat(value)) && isFinite(value)
      default:
        return true
    }
  }

  function validateField(field) {
    const fieldRules = rules[field]
    if (!fieldRules) {
      errors[field] = ''
      return true
    }
    for (const r of fieldRules) {
      if (!checkRule(form[field], r.rule)) {
        errors[field] = r.msg
        return false
      }
    }
    errors[field] = ''
    return true
  }

  function validate() {
    let valid = true
    for (const field in rules) {
      touched[field] = true
      if (!validateField(field)) valid = false
    }
    return valid
  }

  function touch(field) {
    touched[field] = true
    validateField(field)
  }

  const isValid = computed(() => Object.values(errors).every((e) => !e))

  return { errors, touched, isValid, validate, validateField, touch }
}
