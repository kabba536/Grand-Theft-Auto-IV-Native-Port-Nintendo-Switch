#include "telemetry.h"
#include <cassert>
#include <sstream>
#include <string>
using bench_telemetry::Capture;
int main() {
  Capture<2> c; std::ostringstream out;
  c.Record(1, 1); assert(c.size() == 0 && !c.Export(out));
  assert(!c.Start(0) && c.Start(1000) && !c.Start(1000));
  c.Record(10, 4); c.Record(9, 5); c.Record(20, 7); c.Record(30, 8);
  assert(c.size() == 2 && c.Stop() && !c.Stop() && c.Export(out));
  assert(out.str().find("# rejected=2\n") != std::string::npos);
  assert(out.str().find("0,4,10\n1,7,20\n") != std::string::npos);
  assert(c.Start(2000)); c.Record(1, 9); assert(c.Stop());
  std::ostringstream second; assert(c.Export(second));
  assert(second.str().find("# rejected=0\n") != std::string::npos);
  assert(second.str().find("0,9,1\n") != std::string::npos);
}
