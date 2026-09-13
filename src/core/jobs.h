#pragma once
// core/jobs.h — デュアルコア分散。重い処理をcore0ワーカーに投げる。
// loop(通常core1)を塞がないのが目的。 breeding等のμs仕事は直接呼ぶ
// (キュー往復の方が高いため。速さのための正直な使い分け)。
// deep sleep前に必ず完了待ちすること (ToDo完了を待ってから寝る)。
#include <Arduino.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "../env/field.h"
#include "../env/radioseed.h"

namespace jobs {

enum Type : uint8_t { FIELD = 1, SURVEY = 2 };

struct FieldArg {
  field::State* st;
  uint8_t steps;
};
struct SurveyArg {
  radio::Survey* out;
  bool allowBle;
};
struct Job {
  uint8_t type;
  void* arg;
  volatile bool done;
  volatile bool active;
};

inline QueueHandle_t& queueHandle() {
  static QueueHandle_t q = nullptr;
  return q;
}

// 静的ジョブスロット (スタックUse-After-Free撲滅)
inline Job& jobSlot() {
  static Job j{0, nullptr, false, false};
  return j;
}

inline void worker(void*) {
  Job* jp;
  for (;;) {
    if (xQueueReceive(queueHandle(), &jp, portMAX_DELAY) == pdTRUE) {
      if (jp && jp->active) {
        if (jp->type == FIELD && jp->arg) {
          FieldArg* a = (FieldArg*)jp->arg;
          field::advance(*a->st, a->steps);
        } else if (jp->type == SURVEY && jp->arg) {
          SurveyArg* a = (SurveyArg*)jp->arg;
          radio::survey(*a->out, a->allowBle);
        }
        jp->done = true;
        jp->active = false;
      }
    }
  }
}

// 起動時に1回。ワーカーはcore0固定 (loopはcore1)。
inline void init() {
  if (queueHandle()) return;
  queueHandle() = xQueueCreate(2, sizeof(Job*));
  xTaskCreatePinnedToCore(worker, "inkwork", 12288, nullptr, 1, nullptr, 0);
}

// ジョブ投入＋完了待ち。
// 注意: argの指す先は静的寿命にすること。タイムアウト復帰後もワーカーが
// 触り続ける (doRebirthのsv/sa、rtcFieldは該当。スタック変数は禁止)。
inline bool run(uint8_t type, void* arg, uint32_t timeoutMs) {
  QueueHandle_t q = queueHandle();
  if (!q) return false;
  
  Job& j = jobSlot();
  // 前のジョブが残っていれば完了を待つ (安全ガード)
  unsigned long tw0 = millis();
  while (j.active && millis() - tw0 < 2000) delay(2);
  if (j.active) return false;

  j.type = type;
  j.arg = arg;
  j.done = false;
  j.active = true;

  Job* jp = &j;
  if (xQueueSend(q, &jp, 100) != pdTRUE) {
    j.active = false;
    return false;
  }
  unsigned long t0 = millis();
  while (!j.done) {
    if (millis() - t0 > timeoutMs) {
      // タイムアウトしても静的領域のためスタック破壊は発生しない
      return false;
    }
    delay(5);
  }
  return true;
}

}  // namespace jobs
