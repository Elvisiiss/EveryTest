class J17 {

  public static int minSumOfLengths(int[] arr, int target) {
    int sout1 = -1;
    int sout2 = -1;
    boolean qd1 = false;
    boolean qd2 = false;

    // 第一遍遍历，搜索等于target的目标
    for (int i = 0; i < arr.length; i++) {
      if (arr[i] == target) {
        if (qd1 == false) {
          sout1 = 1;
          qd1 = true;
        } else {
          sout2 = 1;
          qd2 = true;
          break;
        }
      }
    }

    // 第二遍遍历，搜索合成目标，此处需要标记等于target的已经算过了。
    int point1 = 0;
    int point2 = 0;
    for (int i = 0; i < arr.length; i++) {

    }

    System.out.println("sout1 = " + sout1);
    System.out.println("sout2 = " + sout2);
    System.out.println("qd1 = " + qd1);
    System.out.println("qd2 = " + qd2);
    if (qd1 && qd2) {
      return sout1 + sout2;
    }
    return -1;
  }

  public static void main(String[] arg) {
    int[] arr = new int[] { 3, 2, 2, 4, 3 };
    int target = 3;
    int out = minSumOfLengths(arr, target);
    System.out.println("return = " + out);
  }
}

/*
 * 数组中一旦有等于target的数据，则两个数字，就有一个是1。
 * 
 */