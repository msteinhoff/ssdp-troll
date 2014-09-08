#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/ip.h>
#include <sys/socket.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main()
{
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock == -1) {
        perror("socket");
        abort();
    }
    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_addr.s_addr = INADDR_ANY,
        .sin_port = 0,
    };
    if (0 != bind(sock, (struct sockaddr *)&addr, sizeof(addr))) {
        perror("bind");
        abort();
    }
    socklen_t addrlen = sizeof(addr);
    if (0 != getsockname(sock, (struct sockaddr *)&addr, &addrlen)) {
        perror("getsockname");
        abort();
    }
    printf("Bound to port %d\n", ntohs(addr.sin_port));
    char opt = 1;
    if (0 != setsockopt(sock, IPPROTO_IP, IP_PKTINFO, &opt, sizeof(opt))) {
        perror("setsockopt");
        abort();
    }
    while (1) {
        char cmbuf[0x100];
        struct sockaddr_in peeraddr;
        struct msghdr mh = {
            .msg_name = &peeraddr,
            .msg_namelen = sizeof(peeraddr),
            .msg_control = cmbuf,
            .msg_controllen = sizeof(cmbuf),
        };
        ssize_t sz = recvmsg(sock, &mh, 0);
        if (sz == -1) {
            perror("recvmsg");
            abort();
        }
        for (
            struct cmsghdr *cmsg = CMSG_FIRSTHDR(&mh);
            cmsg != NULL;
            cmsg = CMSG_NXTHDR(&mh, cmsg))
        {
            if (cmsg->cmsg_level != IPPROTO_IP ||
                cmsg->cmsg_type != IP_PKTINFO)
            {
                continue;
            }
            struct in_pktinfo *pi = CMSG_DATA(cmsg);
            char *spec_dst_str = strdup(inet_ntoa(pi->ipi_spec_dst));
            char *addr_str = strdup(inet_ntoa(pi->ipi_addr));
            printf(
                "recvmsg: name=%s:%d, ifindex=%d, spec_dst=%s, addr=%s, payload=%s\n",
                inet_ntoa(peeraddr.sin_addr),
                ntohs(peeraddr.sin_port),
                pi->ipi_ifindex,
                spec_dst_str,
                addr_str
            );
        }
    }
    return 0;
}
