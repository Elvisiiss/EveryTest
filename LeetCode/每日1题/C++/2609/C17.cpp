#include <algorithm>
#include <climits>
#include <iostream>
#include <vector>
using namespace std;

/**
 * 1477. 找两个和为目标值且不重叠的子数组
 *
 * 思路：
 * 1. 滑动窗口（左→右）找所有和为 target 的子数组，得到 leftMin[]
 * 2. 滑动窗口（右→左）找所有和为 target 的子数组，得到 rightMin[]
 * 3. 在每个位置 j "切一刀"，leftMin[j] + rightMin[j+1] 取最小
 */

class Solution {
public:
  int minSumOfLengths(vector<int> &arr, int target) {
    int n = arr.size();
    int INF = INT_MAX / 2;

    // ============================================================
    // 第一步：从左到右做一次滑动窗口，算出 leftMin[]
    // leftMin[i] = 在 0~i 范围内，和为 target 的最短子数组长度
    // ============================================================

    vector<int> leftMin(n, INF);
    int windowSum = 0; // 当前窗口内元素的和
    int left = 0;      // 窗口的左边界

    for (int right = 0; right < n; right++) {
      // 把右边新元素加入窗口
      windowSum += arr[right];

      // 如果窗口和超过了 target，就缩小窗口（左边界右移）
      while (windowSum > target && left <= right) {
        windowSum -= arr[left];
        left++;
      }

      // 如果窗口和恰好等于 target，记录长度
      if (windowSum == target) {
        leftMin[right] = right - left + 1;
      }
    }

    // 传播最小值：把"在 right 处结束的最短长度"向后推
    for (int i = 1; i < n; i++) {
      leftMin[i] = min(leftMin[i], leftMin[i - 1]);
    }

    // ============================================================
    // 第二步：从右到左做一次滑动窗口，算出 rightMin[]
    // rightMin[i] = 在 i~n-1 范围内，和为 target 的最短子数组长度
    // ============================================================

    vector<int> rightMin(n, INF);
    windowSum = 0;
    int rightBound = n - 1; // 窗口的右边界

    for (int i = n - 1; i >= 0; i--) {
      // 把左边新元素加入窗口
      windowSum += arr[i];

      // 如果窗口和超过了 target，就缩小窗口（右边界左移）
      while (windowSum > target && rightBound >= i) {
        windowSum -= arr[rightBound];
        rightBound--;
      }

      // 如果窗口和恰好等于 target，记录长度
      if (windowSum == target) {
        rightMin[i] = rightBound - i + 1;
      }
    }

    // 传播最小值：把"在 left 处开始的最短长度"向前推
    for (int i = n - 2; i >= 0; i--) {
      rightMin[i] = min(rightMin[i], rightMin[i + 1]);
    }

    // ============================================================
    // 第三步：在每个位置 j "切一刀"，取最小的长度和
    // ============================================================

    int answer = INF;
    for (int j = 0; j < n - 1; j++) {
      answer = min(answer, leftMin[j] + rightMin[j + 1]);
    }

    return answer >= INF ? -1 : answer;
  }
};

int main() {
  Solution s;

  cout << s.minSumOfLengths(*new vector<int>{3, 2, 2, 4, 3}, 3) << endl;           // 2
  cout << s.minSumOfLengths(*new vector<int>{7, 3, 4, 7}, 7) << endl;              // 2
  cout << s.minSumOfLengths(*new vector<int>{4, 3, 2, 6, 2, 3, 4}, 6) << endl;     // -1
  cout << s.minSumOfLengths(*new vector<int>{5, 5, 4, 4, 5}, 3) << endl;           // -1
  cout << s.minSumOfLengths(*new vector<int>{3, 1, 1, 1, 5, 1, 2, 1}, 3) << endl;  // 3

  return 0;
}
