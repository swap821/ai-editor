import fs from 'node:fs'

const reportPath = process.argv[2]
if (!reportPath) {
  console.error('usage: node check_frontend_warning_budget.mjs eslint-report.json')
  process.exit(2)
}

const budgetPath = new URL('../.aios/state/FRONTEND_WARNING_BUDGET.json', import.meta.url)
const budget = JSON.parse(fs.readFileSync(budgetPath, 'utf8'))
const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'))
const warnings = report.reduce((total, file) => total + Number(file.warningCount || 0), 0)
const limit = Number(budget.maxWarnings)
if (!Number.isFinite(limit) || warnings > limit) {
  console.error(`frontend warning budget exceeded: ${warnings} > ${limit}`)
  process.exit(1)
}
console.log(`frontend warning budget: ${warnings}/${limit}; next target ${budget.nextTarget}`)
