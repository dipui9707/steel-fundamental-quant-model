#!/usr/bin/env python3
"""阶段E安全入口：每次创建独立实验，禁止覆盖旧回测或真实交易台账。"""
from run_framework_experiment import run

if __name__ == '__main__':
    run()
