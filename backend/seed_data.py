import json
import logging
from pathlib import Path

from models import CourseVideo

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"


def load_course_videos():
    path = _DATA_DIR / "courses.json"
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    return [CourseVideo(**item) for item in items]


def seed_courses(db):
    from models import CourseVideo as CV
    CV.query.delete()
    db.session.add_all(load_course_videos())
    db.session.commit()
    logger.info("Course videos seeded from courses.json")


def seed_textbooks(db):
    from models import Textbook

    if Textbook.query.first() is not None:
        return

    textbooks = [
        Textbook(
            title="计算机网络原理",
            description="系统讲解计算机网络的基本概念和原理",
            category="基础理论",
            content="""# 计算机网络基础知识

## 1. 网络的定义
计算机网络是指将地理位置不同的具有独立功能的多台计算机及其外部设备，通过通信线路连接起来，在网络操作系统、网络管理软件及网络通信协议的管理和协调下，实现资源共享和信息传递的计算机系统。

## 2. 网络的功能
- 资源共享：硬件资源、软件资源、信息资源
- 数据通信：高效、可靠的数据传输
- 提高可靠性：通过冗余路由提高系统可靠性
- 负载均衡：分散系统负载，提高工作效率

## 3. 网络的分类
根据覆盖范围：
- 局域网(LAN)：通常在几百米以内
- 城域网(MAN)：覆盖一个城市
- 广域网(WAN)：覆盖较大的地理范围""",
        ),
        Textbook(
            title="TCP/IP 协议详解",
            description="深入学习 TCP/IP 协议族的工作原理",
            category="协议详解",
            content="""# TCP/IP 协议族详解

## 1. TCP/IP 概述
TCP/IP 是互联网的基础协议族，由众多协议组成，实现了计算机的网络通信。

## 2. IP 协议（网络层）
功能：
- 提供无连接、不可靠的数据报传递
- 进行路由和转发
- 处理数据包的分片和重组

## 3. TCP 协议（传输层）
特点：
- 面向连接的协议
- 提供可靠的、有序的数据传输
- 使用流量控制和拥塞控制
- 支持全双工通信""",
        ),
    ]
    db.session.add_all(textbooks)
    db.session.commit()
    logger.info("Textbooks seeded")
