import unittest
from starter_arena.__main__ import allocations, shortest_path, market_demo, ml_demo, game_demo, coding_demo

class TestStarter(unittest.TestCase):
    def test_allocation_exact(self):
        self.assertEqual(allocations(3,[1,2],[3,3]),(6,(0,3)))
    def test_allocation_no_solution(self):
        self.assertEqual(allocations(5,[1],[4]),(-float('inf'),None))
    def test_graph(self):
        self.assertEqual(shortest_path({'a':[('b',2),('c',10)],'b':[('c',3)]},'a','c'),5)
        self.assertIsNone(shortest_path({},'a','c'))
    def test_negative_weights(self):
        with self.assertRaises(ValueError):shortest_path({'a':[('b',-1)]},'a','b')
    def test_reproducible(self):
        self.assertEqual(market_demo(11),market_demo(11))
    def test_modules_smoke(self):
        self.assertEqual(ml_demo()['test_rows'],6)
        self.assertEqual(sum(game_demo()['allocations']),8)
        self.assertEqual(coding_demo()['shortest_A_to_D'],4)
if __name__=='__main__':unittest.main()
