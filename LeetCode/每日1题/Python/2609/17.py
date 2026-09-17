"""
1477. 找两个和为目标值且不重叠的子数组

核心思路：
1. 用"滑动窗口"找出数组中所有和恰好等于 target 的子数组
2. 用"前缀最小值 + 后缀最小值"的技巧，快速找到最优的不重叠配对
"""

from typing import List


class Solution:
    def minSumOfLengths(self, arr: List[int], target: int) -> int:

        n = len(arr)

        # ============================================================
        # 第一步：从左到右做一次滑动窗口
        # 目的：求出 left_min[i]，表示"在 0~i 这个范围内，
        #        最短的、和为 target 的子数组的长度"
        # ============================================================

        left_min = [float('inf')] * n  # 先全部设为无穷大（表示还没找到）
        window_sum = 0  # 当前窗口内元素的和
        left = 0  # 窗口的左边界（滑动窗口靠这个指针来"收缩"）

        # right 是窗口的右边界，我们用 for 循环一步步向右扩展
        for right in range(n):

            # 把右边新元素加入窗口
            window_sum += arr[right]

            # 如果窗口内的和超过了 target，就把左边界右移（缩小窗口）
            # 注意：因为所有数字都是正数，缩小窗口只会让和变小
            while window_sum > target and left <= right:
                window_sum -= arr[left]
                left += 1

            # 如果窗口内的和恰好等于 target，说明 arr[left..right] 是一个答案
            if window_sum == target:
                left_min[right] = right - left + 1  # 只记录"在 right 处结束"的最短长度

        # 【关键优化】把"在 right 处结束的最短长度"向后传播
        # 比如 left_min[5] = 2，那 left_min[6] 至少不会比 2 更差
        # 这样一趟 O(n) 的遍历就替代了之前 O(n²) 的内层 for 循环
        for i in range(1, n):
            left_min[i] = min(left_min[i], left_min[i - 1])

        # ============================================================
        # 第二步：从右到左做一次滑动窗口
        # 目的：求出 right_min[i]，表示"在 i~n-1 这个范围内，
        #        最短的、和为 target 的子数组的长度"
        # ============================================================

        right_min = [float('inf')] * n  # 同样先全部设为无穷大
        window_sum = 0
        right = n - 1  # 这次窗口的右边界从最右边开始

        # left 从右往左遍历，作为窗口的左边界
        for left in range(n - 1, -1, -1):

            # 把左边新元素加入窗口
            window_sum += arr[left]

            # 如果窗口内的和超过了 target，就把右边界左移（缩小窗口）
            while window_sum > target and right >= left:
                window_sum -= arr[right]
                right -= 1

            # 如果窗口内的和恰好等于 target，说明 arr[left..right] 是一个答案
            if window_sum == target:
                right_min[left] = right - left + 1  # 只记录"在 left 处开始"的最短长度

        # 【关键优化】与第一步同理，向前传播最小值
        for i in range(n - 2, -1, -1):
            right_min[i] = min(right_min[i], right_min[i + 1])

        # ============================================================
        # 第三步：合并两个数组，找出最优答案
        #
        # 关键思想：
        #   我们在位置 j 处"切一刀"，把数组分成左右两半：
        #   - 左半 [0..j]   中最短的和为 target 的子数组长度 = left_min[j]
        #   - 右半 [j+1..n-1] 中最短的和为 target 的子数组长度 = right_min[j+1]
        #   两半互不重叠！长度和 = left_min[j] + right_min[j+1]
        #
        #   我们遍历所有可能的切点 j，取最小的长度和即可。
        # ============================================================

        answer = float('inf')

        for j in range(n - 1):  # j 从 0 到 n-2（右半至少要留一个位置）
            # 如果左右两边都找到了和为 target 的子数组
            if left_min[j] != float('inf') and right_min[j + 1] != float('inf'):
                answer = min(answer, left_min[j] + right_min[j + 1])

        # 如果 answer 还是无穷大，说明找不到两个不重叠的子数组，返回 -1
        return -1 if answer == float('inf') else answer


# ============================================================
# 测试一下
# ============================================================
if __name__ == "__main__":
    s = Solution()

    # 示例1：只有 [3] 和 [3]，长度和 = 2
    print(s.minSumOfLengths([3, 2, 2, 4, 3], 3))  # 输出 2

    # 示例2：可以选择 [7] 和 [7]，长度和 = 2
    print(s.minSumOfLengths([7, 3, 4, 7], 7))  # 输出 2

    # 示例3：只有一个和为6的子数组，凑不齐两个，返回 -1
    print(s.minSumOfLengths([4, 3, 2, 6, 2, 3, 4], 6))  # 输出 -1

    # 示例4：一个和为3的子数组都没有，返回 -1
    print(s.minSumOfLengths([5, 5, 4, 4, 5], 3))  # 输出 -1

    # 示例5：[3] 和 [2,1]，长度和 = 1+2 = 3
    print(s.minSumOfLengths([3, 1, 1, 1, 5, 1, 2, 1], 3))  # 输出 3
