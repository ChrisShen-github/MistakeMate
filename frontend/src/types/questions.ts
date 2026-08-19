export type QuestionOption = { label: string; text: string }
export type QuestionFigure = { id: string; position: number }
export type QuestionAnswerFile = { id: string; original_name: string; content_type: string; size: number; position: number; created_at: string }

export type QuestionPart = {
  id: string
  parent_id: string | null
  position: number
  label: string
  part_type: string
  prompt: string
  answers: string[]
  solution: string
  key_points: string[]
  answer_lines: number
  knowledge_points: string
  difficulty: number
  error_type: string
}

export type MistakeQuestion = {
  id: string
  position: number
  question_type: string
  stem: string
  options: QuestionOption[]
  correct_answer: string
  explanation: string
  knowledge_points: string
  difficulty: number
  error_type: string
  is_image_only: boolean
  clean_source_file_id: string | null
  parts: QuestionPart[]
  figures: QuestionFigure[]
  answer_files: QuestionAnswerFile[]
  status: string
  updated_at: string
}
