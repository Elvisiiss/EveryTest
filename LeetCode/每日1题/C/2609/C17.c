#include <stdio.h>

/**
 * 1477. 找两个和为目标值且不重叠的子数组
 *
 * 思路：
 * 1. 滑动窗口（左→右）找所有和为 target 的子数组，得到 leftMin[]
 * 2. 滑动窗口（右→左）找所有和为 target 的子数组，得到 rightMin[]
 * 3. 在每个位置 j "切一刀"，leftMin[j] + rightMin[j+1] 取最小
 */

#define INF 1000000000

int minSumOfLengths(int *arr, int arrSize, int target) {
  int n = arrSize;

  /* ============================================================
   * 第一步：从左到右做一次滑动窗口，算出 leftMin[]
   * leftMin[i] = 在 0~i 范围内，和为 target 的最短子数组长度
   * ============================================================ */

  int leftMin[n];
  int rightMin[n];
  for (int i = 0; i < n; i++) {
    leftMin[i] = INF;
    rightMin[i] = INF;
  }

  int windowSum = 0; /* 当前窗口内元素的和 */
  int left = 0;      /* 窗口的左边界 */

  for (int right = 0; right < n; right++) {
    /* 把右边新元素加入窗口 */
    windowSum += arr[right];

    /* 如果窗口和超过了 target，就缩小窗口（左边界右移） */
    while (windowSum > target && left <= right) {
      windowSum -= arr[left];
      left++;
    }

    /* 如果窗口和恰好等于 target，记录长度 */
    if (windowSum == target) {
      leftMin[right] = right - left + 1;
    }
  }

  /* 传播最小值：把"在 right 处结束的最短长度"向后推 */
  for (int i = 1; i < n; i++) {
    if (leftMin[i - 1] < leftMin[i]) {
      leftMin[i] = leftMin[i - 1];
    }
  }

  /* ============================================================
   * 第二步：从右到左做一次滑动窗口，算出 rightMin[]
   * rightMin[i] = 在 i~n-1 范围内，和为 target 的最短子数组长度
   * ============================================================ */

  windowSum = 0;
  int rightBound = n - 1; /* 窗口的右边界 */

  for (int i = n - 1; i >= 0; i--) {
    /* 把左边新元素加入窗口 */
    windowSum += arr[i];

    /* 如果窗口和超过了 target，就缩小窗口（右边界左移） */
    while (windowSum > target && rightBound >= i) {
      windowSum -= arr[rightBound];
      rightBound--;
    }

    /* 如果窗口和恰好等于 target，记录长度 */
    if (windowSum == target) {
      rightMin[i] = rightBound - i + 1;
    }
  }

  /* 传播最小值：把"在 left 处开始的最短长度"向前推 */
  for (int i = n - 2; i >= 0; i--) {
    if (rightMin[i + 1] < rightMin[i]) {
      rightMin[i] = rightMin[i + 1];
    }
  }

  /* ============================================================
   * 第三步：在每个位置 j "切一刀"，取最小的长度和
   * 左半 [0..j] 的最优解 + 右半 [j+1..n-1] 的最优解
   * ============================================================ */

  int answer = INF;
  for (int j = 0; j < n - 1; j++) {
    int sum = leftMin[j] + rightMin[j + 1];
    if (sum < answer) {
      answer = sum;
    }
  }

  /* 如果答案还是 INF，说明找不到两个不重叠的子数组 */
  return answer >= INF ? -1 : answer;
}

int main() {
  int a1[] = {3, 2, 2, 4, 3};
  int a2[] = {7, 3, 4, 7};
  int a3[] = {4, 3, 2, 6, 2, 3, 4};
  int a4[] = {5, 5, 4, 4, 5};
  int a5[] = {3, 1, 1, 1, 5, 1, 2, 1};

  printf("%d\n", minSumOfLengths(a1, 5, 3));   /* 2 */
  printf("%d\n", minSumOfLengths(a2, 4, 7));   /* 2 */
  printf("%d\n", minSumOfLengths(a3, 7, 6));   /* -1 */
  printf("%d\n", minSumOfLengths(a4, 5, 3));   /* -1 */
  printf("%d\n", minSumOfLengths(a5, 8, 3));   /* 3 */

  return 0;
}
